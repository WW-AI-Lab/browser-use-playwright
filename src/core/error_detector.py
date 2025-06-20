"""
错误检测和分析器
负责捕获、分析和分类执行错误，为自愈功能提供基础数据
"""

import os
import json
import uuid
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from playwright.async_api import Page, Error as PlaywrightError

from ..models.error import (
    ErrorContext, ErrorType, ErrorSeverity, FailurePoint,
    HealingStatus
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ErrorDetector:
    """错误检测和分析器"""
    
    def __init__(self, screenshot_dir: str = "logs/screenshots", dom_dir: str = "logs/dom"):
        self.screenshot_dir = Path(screenshot_dir)
        self.dom_dir = Path(dom_dir)
        
        # 确保目录存在
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.dom_dir.mkdir(parents=True, exist_ok=True)
        
        # 错误分类规则
        self.error_patterns = {
            ErrorType.ELEMENT_NOT_FOUND: [
                "element not found",
                "no such element",
                "selector not found",
                "element is not visible",
                "element is not clickable"
            ],
            ErrorType.TIMEOUT: [
                "timeout",
                "timed out",
                "wait timeout",
                "navigation timeout"
            ],
            ErrorType.NETWORK_ERROR: [
                "network error",
                "connection refused",
                "dns resolution failed",
                "net::err_"
            ],
            ErrorType.PAGE_LOAD_ERROR: [
                "page load failed",
                "navigation failed",
                "page crashed"
            ],
            ErrorType.JAVASCRIPT_ERROR: [
                "javascript error",
                "script error",
                "evaluation failed"
            ],
            ErrorType.SELECTOR_INVALID: [
                "invalid selector",
                "malformed selector",
                "syntax error in selector"
            ],
            ErrorType.PERMISSION_DENIED: [
                "permission denied",
                "access denied",
                "forbidden"
            ]
        }
        
        # 严重程度映射
        self.severity_mapping = {
            ErrorType.ELEMENT_NOT_FOUND: ErrorSeverity.MEDIUM,
            ErrorType.TIMEOUT: ErrorSeverity.MEDIUM,
            ErrorType.NETWORK_ERROR: ErrorSeverity.HIGH,
            ErrorType.PAGE_LOAD_ERROR: ErrorSeverity.HIGH,
            ErrorType.JAVASCRIPT_ERROR: ErrorSeverity.LOW,
            ErrorType.SELECTOR_INVALID: ErrorSeverity.LOW,
            ErrorType.PERMISSION_DENIED: ErrorSeverity.CRITICAL,
            ErrorType.UNKNOWN: ErrorSeverity.MEDIUM
        }
    
    async def capture_error_context(
        self,
        error: Exception,
        step: Dict[str, Any],
        step_index: int,
        workflow_path: str,
        page: Optional[Page] = None,
        execution_context: Optional[Dict[str, Any]] = None
    ) -> ErrorContext:
        """捕获错误上下文信息"""
        try:
            error_id = str(uuid.uuid4())
            logger.info(f"开始捕获错误上下文: {error_id}")
            
            # 分类错误
            error_type = self.classify_error(error)
            severity = self.severity_mapping.get(error_type, ErrorSeverity.MEDIUM)
            
            # 基础错误信息
            error_message = str(error)
            error_details = error.__class__.__name__ + ": " + error_message
            
            # 页面状态信息
            page_url = None
            page_title = None
            screenshot_path = None
            dom_snapshot = None
            browser_type = None
            viewport_size = None
            user_agent = None
            
            if page:
                try:
                    page_url = page.url
                    page_title = await page.title()
                    browser_type = page.context.browser.browser_type.name
                    viewport_size = page.viewport_size
                    user_agent = await page.evaluate("navigator.userAgent")
                    
                    # 截图
                    screenshot_path = await self._capture_screenshot(page, error_id)
                    
                    # DOM快照
                    dom_snapshot = await self._capture_dom_snapshot(page, error_id)
                    
                except Exception as e:
                    logger.warning(f"捕获页面状态时出错: {e}")
            
            # 创建错误上下文
            error_context = ErrorContext(
                error_id=error_id,
                error_type=error_type,
                error_message=error_message,
                error_details=error_details,
                severity=severity,
                workflow_path=workflow_path,
                step_index=step_index,
                step_data=step,
                page_url=page_url,
                page_title=page_title,
                screenshot_path=screenshot_path,
                dom_snapshot=dom_snapshot,
                browser_type=browser_type,
                viewport_size=viewport_size,
                user_agent=user_agent,
                execution_context=execution_context or {}
            )
            
            # 判断是否可自愈
            error_context.is_healable = await self.is_healable(error_context)
            
            logger.info(f"错误上下文捕获完成: {error_id}, 类型: {error_type}, 可自愈: {error_context.is_healable}")
            return error_context
            
        except Exception as e:
            logger.error(f"捕获错误上下文失败: {e}")
            # 返回基础错误上下文
            return ErrorContext(
                error_id=str(uuid.uuid4()),
                error_type=ErrorType.UNKNOWN,
                error_message=str(error),
                severity=ErrorSeverity.HIGH,
                workflow_path=workflow_path,
                step_index=step_index,
                step_data=step,
                is_healable=False
            )
    
    def classify_error(self, error: Exception) -> ErrorType:
        """分类错误类型"""
        error_message = str(error).lower()
        error_type_name = type(error).__name__.lower()
        
        # 优先检查异常类型
        if "timeout" in error_type_name:
            return ErrorType.TIMEOUT
        
        # 然后检查错误消息
        for error_type, patterns in self.error_patterns.items():
            for pattern in patterns:
                if pattern in error_message:
                    return error_type
        
        # 特殊处理一些常见的异常类型
        if "asyncio.timeouterror" in error_type_name:
            return ErrorType.TIMEOUT
        elif "playwright" in error_type_name and "timeout" in error_message:
            return ErrorType.TIMEOUT
        elif "element" in error_message and "not found" in error_message:
            return ErrorType.ELEMENT_NOT_FOUND
        elif "步骤执行超时" in str(error):
            return ErrorType.TIMEOUT
        elif "execution timeout" in error_message:
            return ErrorType.TIMEOUT
        
        return ErrorType.UNKNOWN
    
    async def is_healable(self, error_context: ErrorContext) -> bool:
        """判断错误是否可自愈"""
        # 严重程度为CRITICAL的错误不可自愈
        if error_context.severity == ErrorSeverity.CRITICAL:
            return False
        
        # 某些特定错误类型可自愈
        healable_types = [
            ErrorType.ELEMENT_NOT_FOUND,
            ErrorType.TIMEOUT,
            ErrorType.JAVASCRIPT_ERROR,
            ErrorType.SELECTOR_INVALID
        ]
        
        # 检查错误类型是否在可自愈列表中
        if error_context.error_type in healable_types:
            return True
        
        # 基于错误消息的额外判断
        error_message = error_context.error_message.lower()
        
        # 超时相关错误都可以尝试自愈
        if any(keyword in error_message for keyword in [
            "timeout", "超时", "timed out", "execution timeout",
            "步骤执行超时", "wait timeout"
        ]):
            return True
        
        # 元素相关错误可以尝试自愈
        if any(keyword in error_message for keyword in [
            "element not found", "selector", "not visible",
            "not clickable", "元素未找到"
        ]):
            return True
        
        # 默认情况下，严重程度为LOW或MEDIUM的错误可以尝试自愈
        if error_context.severity in [ErrorSeverity.LOW, ErrorSeverity.MEDIUM]:
            return True
        
        return False
    
    async def locate_failure_point(
        self,
        workflow: Dict[str, Any],
        failed_step_index: int
    ) -> FailurePoint:
        """定位失败点"""
        try:
            steps = workflow.get("steps", [])
            if failed_step_index >= len(steps):
                raise ValueError(f"步骤索引超出范围: {failed_step_index}")
            
            failed_step = steps[failed_step_index]
            
            failure_point = FailurePoint(
                step_index=failed_step_index,
                step_type=failed_step.get("type", "unknown"),
                selector=failed_step.get("selector"),
                action=failed_step.get("action"),
                target_element=failed_step.get("element_description"),
                expected_state=failed_step.get("expected_state"),
                actual_state=failed_step.get("actual_state")
            )
            
            return failure_point
            
        except Exception as e:
            logger.error(f"定位失败点时出错: {e}")
            return FailurePoint(
                step_index=failed_step_index,
                step_type="unknown"
            )
    
    async def _capture_screenshot(self, page: Page, error_id: str) -> Optional[str]:
        """捕获页面截图"""
        try:
            screenshot_path = self.screenshot_dir / f"error_{error_id}.png"
            await page.screenshot(path=str(screenshot_path), full_page=True)
            return str(screenshot_path)
        except Exception as e:
            logger.warning(f"截图失败: {e}")
            return None
    
    async def _capture_dom_snapshot(self, page: Page, error_id: str) -> Optional[str]:
        """捕获DOM快照"""
        try:
            dom_path = self.dom_dir / f"error_{error_id}.html"
            
            # 获取页面HTML
            html_content = await page.content()
            
            # 保存到文件
            with open(dom_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            return str(dom_path)
        except Exception as e:
            logger.warning(f"DOM快照失败: {e}")
            return None
    
    async def analyze_error_pattern(self, error_contexts: List[ErrorContext]) -> Dict[str, Any]:
        """分析错误模式"""
        if not error_contexts:
            return {}
        
        # 统计错误类型
        error_type_counts = {}
        severity_counts = {}
        
        for context in error_contexts:
            error_type_counts[context.error_type] = error_type_counts.get(context.error_type, 0) + 1
            severity_counts[context.severity] = severity_counts.get(context.severity, 0) + 1
        
        # 计算自愈成功率
        healable_count = sum(1 for ctx in error_contexts if ctx.is_healable)
        success_count = sum(1 for ctx in error_contexts if ctx.healing_status == HealingStatus.SUCCESS)
        
        healing_success_rate = success_count / healable_count if healable_count > 0 else 0
        
        return {
            "total_errors": len(error_contexts),
            "error_type_distribution": error_type_counts,
            "severity_distribution": severity_counts,
            "healable_count": healable_count,
            "healing_success_rate": healing_success_rate,
            "most_common_error": max(error_type_counts, key=error_type_counts.get) if error_type_counts else None
        }
    
    async def save_error_context(self, error_context: ErrorContext, save_dir: str = "logs/errors") -> str:
        """保存错误上下文到文件"""
        try:
            save_path = Path(save_dir)
            save_path.mkdir(parents=True, exist_ok=True)
            
            file_path = save_path / f"error_{error_context.error_id}.json"
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(error_context.dict(), f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"错误上下文已保存: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"保存错误上下文失败: {e}")
            raise
    
    async def load_error_context(self, error_id: str, save_dir: str = "logs/errors") -> Optional[ErrorContext]:
        """从文件加载错误上下文"""
        try:
            file_path = Path(save_dir) / f"error_{error_id}.json"
            
            if not file_path.exists():
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return ErrorContext(**data)
            
        except Exception as e:
            logger.error(f"加载错误上下文失败: {e}")
            return None 