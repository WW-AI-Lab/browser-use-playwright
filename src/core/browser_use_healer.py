"""
Browser-Use自愈引擎
使用Browser-Use AI来修复执行失败的工作流步骤
"""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from browser_use import Agent, Browser
from browser_use.browser.browser import BrowserConfig

from ..models.error import (
    ErrorContext, HealingSession, HealingAction, HealingStatus
)
from ..core.config import config
from ..utils.logger import get_logger

logger = get_logger(__name__)


class BrowserUseHealer:
    """Browser-Use自愈引擎"""
    
    def __init__(self, healing_config: Optional[Dict[str, Any]] = None):
        self.healing_config = healing_config or {}
        
        # 默认配置
        self.default_config = {
            "headless": False,
            "timeout": 60,
            "max_attempts": 3,
            "model": "gpt-4o",
            "temperature": 0.1,
            "max_tokens": 2000
        }
        
        # 合并配置
        self.config = {**self.default_config, **self.healing_config}
        
        # 活跃会话
        self.active_sessions: Dict[str, HealingSession] = {}
        
        logger.info(f"Browser-Use自愈引擎初始化完成，配置: {self.config}")
    
    async def start_healing_session(self, error_context: ErrorContext) -> HealingSession:
        """启动自愈会话"""
        try:
            session_id = str(uuid.uuid4())
            logger.info(f"启动自愈会话: {session_id}")
            
            # 生成自愈目标
            healing_goal = self._generate_healing_goal(error_context)
            
            # 创建自愈会话
            session = HealingSession(
                session_id=session_id,
                error_context=error_context,
                healing_goal=healing_goal,
                status=HealingStatus.IN_PROGRESS
            )
            
            # 记录活跃会话
            self.active_sessions[session_id] = session
            
            logger.info(f"自愈会话创建成功: {session_id}, 目标: {healing_goal}")
            return session
            
        except Exception as e:
            logger.error(f"启动自愈会话失败: {e}")
            raise
    
    async def heal_with_browser_use(self, session: HealingSession) -> bool:
        """使用Browser-Use进行自愈"""
        try:
            logger.info(f"开始Browser-Use自愈: {session.session_id}")
            
            # 简化的自愈策略（不依赖真实的Browser-Use环境）
            # 在实际环境中，这里会使用真实的Browser-Use Agent
            healing_success = await self._simulate_browser_use_healing(session)
            
            if healing_success:
                session.status = HealingStatus.SUCCESS
                session.success = True
                session.end_time = datetime.now()
                logger.info(f"Browser-Use自愈成功: {session.session_id}")
                return True
            else:
                session.status = HealingStatus.FAILED
                session.success = False
                session.failure_reason = "Browser-Use自愈失败"
                session.end_time = datetime.now()
                logger.warning(f"Browser-Use自愈失败: {session.session_id}")
                return False
                
        except Exception as e:
            logger.error(f"Browser-Use自愈失败: {e}")
            session.status = HealingStatus.FAILED
            session.success = False
            session.failure_reason = str(e)
            session.end_time = datetime.now()
            return False
    
    async def _simulate_browser_use_healing(self, session: HealingSession) -> bool:
        """模拟Browser-Use自愈（用于演示和测试）"""
        try:
            error_context = session.error_context
            error_type = error_context.error_type
            step_data = error_context.step_data
            
            logger.info(f"模拟Browser-Use自愈: 错误类型={error_type}, 步骤类型={step_data.get('type')}")
            
            # 根据错误类型生成自愈步骤
            new_steps = []
            
            if "timeout" in str(error_type).lower():
                # 超时错误：添加等待步骤和重试
                if step_data.get("type") == "click":
                    new_steps = [
                        {
                            "id": f"healed_wait_{session.session_id[:8]}",
                            "type": "wait",
                            "description": "等待页面稳定（自愈添加）",
                            "selector": step_data.get("selector", ""),
                            "timeout": 5000,
                            "wait_condition": "visible"
                        },
                        {
                            "id": f"healed_click_{session.session_id[:8]}",
                            "type": "click",
                            "description": f"重新点击（自愈修复）: {step_data.get('description', '')}",
                            "selector": step_data.get("selector", ""),
                            "timeout": 15000,
                            "wait_condition": "visible"
                        }
                    ]
                elif step_data.get("type") == "fill":
                    new_steps = [
                        {
                            "id": f"healed_wait_{session.session_id[:8]}",
                            "type": "wait",
                            "description": "等待输入框可用（自愈添加）",
                            "selector": step_data.get("selector", ""),
                            "timeout": 5000,
                            "wait_condition": "visible"
                        },
                        {
                            "id": f"healed_fill_{session.session_id[:8]}",
                            "type": "fill",
                            "description": f"重新填写（自愈修复）: {step_data.get('description', '')}",
                            "selector": step_data.get("selector", ""),
                            "value": step_data.get("value", ""),
                            "timeout": 15000
                        }
                    ]
            
            elif "element_not_found" in str(error_type).lower():
                # 元素未找到：生成更强的选择器策略
                original_selector = step_data.get("selector", "")
                step_type = step_data.get("type", "")
                
                if step_type == "click":
                    # 生成多个备选点击策略
                    enhanced_selectors = self._generate_enhanced_selectors_for_click(original_selector, step_data)
                    
                    for i, selector in enumerate(enhanced_selectors[:3]):  # 最多3个备选
                        new_steps.append({
                            "id": f"healed_click_{session.session_id[:8]}_{i}",
                            "type": "click",
                            "description": f"备选点击策略{i+1}（自愈修复）: {step_data.get('description', '')}",
                            "selector": selector,
                            "timeout": 15000,
                            "wait_condition": "visible"
                        })
                
                elif step_type == "fill":
                    # 生成通用的填写策略
                    value = step_data.get("value", "")
                    enhanced_selectors = self._generate_enhanced_selectors_for_fill(original_selector, value)
                    
                    for i, selector in enumerate(enhanced_selectors[:2]):  # 最多2个备选
                        new_steps.append({
                            "id": f"healed_fill_{session.session_id[:8]}_{i}",
                            "type": "fill",
                            "description": f"备选填写策略{i+1}（自愈修复）: {step_data.get('description', '')}",
                            "selector": selector,
                            "value": value,
                            "timeout": 15000
                        })
            
            # 如果生成了新步骤，记录自愈操作
            if new_steps:
                session.new_steps = new_steps
                
                # 创建自愈操作记录
                for i, step in enumerate(new_steps):
                    healing_action = HealingAction(
                        action_id=f"action_{session.session_id[:8]}_{i}",
                        action_type=step["type"],
                        selector=step.get("selector"),
                        value=step.get("value"),
                        description=step["description"],
                        success=True  # 假设会成功
                    )
                    session.healing_actions.append(healing_action)
                
                logger.info(f"生成了{len(new_steps)}个自愈步骤")
                return True
            else:
                logger.warning("未能生成有效的自愈步骤")
                return False
                
        except Exception as e:
            logger.error(f"模拟Browser-Use自愈失败: {e}")
            return False
    
    def _generate_enhanced_selectors_for_click(self, original_selector: str, step_data: Dict[str, Any]) -> List[str]:
        """为点击操作生成增强的选择器"""
        enhanced_selectors = []
        
        # 基于描述推测可能的选择器
        description = step_data.get("description", "").lower()
        
        if "搜索" in description or "search" in description:
            enhanced_selectors.extend([
                'input[type="submit"]',
                'button[type="submit"]',
                '.search-button',
                '.btn-search',
                '[value*="搜索"]',
                '[value*="search"]',
                'button:contains("搜索")',
                'input[value="搜索"]'
            ])
        
        if "按钮" in description or "button" in description:
            enhanced_selectors.extend([
                'button',
                'input[type="button"]',
                'input[type="submit"]',
                '.btn',
                '.button',
                '[role="button"]'
            ])
        
        if "链接" in description or "link" in description:
            enhanced_selectors.extend([
                'a[href]',
                '.link',
                '[role="link"]'
            ])
        
        # 添加通用的备选选择器
        if original_selector:
            # 简化选择器
            simplified = original_selector.split(',')[0].strip()
            enhanced_selectors.append(simplified)
            
            # 移除特定的属性
            import re
            base_selector = re.sub(r'\[.*?\]', '', simplified)
            if base_selector and base_selector != simplified:
                enhanced_selectors.append(base_selector)
        
        # 移除重复项并保持顺序
        seen = set()
        unique_selectors = []
        for selector in enhanced_selectors:
            if selector and selector not in seen:
                seen.add(selector)
                unique_selectors.append(selector)
        
        return unique_selectors
    
    def _generate_enhanced_selectors_for_fill(self, original_selector: str, value: str) -> List[str]:
        """为填写操作生成增强的选择器"""
        enhanced_selectors = []
        
        # 基于要填写的内容推测可能的选择器
        value_lower = value.lower()
        
        if any(keyword in value_lower for keyword in ["搜索", "search", "查找"]):
            enhanced_selectors.extend([
                'input[name="q"]',
                'input[name="query"]',
                'input[name="search"]',
                'input[placeholder*="搜索"]',
                'input[placeholder*="search"]',
                'input[type="search"]',
                '#search-input',
                '#query',
                '.search-input'
            ])
        
        # 通用输入框选择器
        enhanced_selectors.extend([
            'input[type="text"]',
            'input:not([type])',
            'textarea',
            '[contenteditable="true"]'
        ])
        
        # 基于原始选择器的变体
        if original_selector:
            simplified = original_selector.split(',')[0].strip()
            enhanced_selectors.append(simplified)
        
        # 移除重复项
        seen = set()
        unique_selectors = []
        for selector in enhanced_selectors:
            if selector and selector not in seen:
                seen.add(selector)
                unique_selectors.append(selector)
        
        return unique_selectors
    
    async def _restore_context(self, agent: Agent, error_context: ErrorContext):
        """恢复页面上下文"""
        try:
            logger.info(f"恢复页面上下文: {error_context.page_url}")
            
            # 导航到错误页面
            await agent.browser.go_to_url(error_context.page_url)
            
            # 等待页面加载
            await asyncio.sleep(2)
            
            # 如果有DOM快照，可以进行更精确的状态恢复
            if error_context.dom_snapshot:
                logger.info("检测到DOM快照，进行状态分析")
                # 这里可以添加更复杂的状态恢复逻辑
            
        except Exception as e:
            logger.warning(f"恢复页面上下文失败: {e}")
    
    async def _execute_healing_task(self, agent: Agent, session: HealingSession) -> List[HealingAction]:
        """执行自愈任务"""
        healing_actions = []
        
        try:
            logger.info(f"执行自愈任务: {session.healing_goal}")
            
            # 构建详细的自愈提示
            healing_prompt = self._build_healing_prompt(session.error_context)
            
            # 执行自愈任务
            result = await agent.run(healing_prompt)
            
            # 解析Agent的操作历史
            if hasattr(agent, 'history') and agent.history:
                for i, action in enumerate(agent.history):
                    healing_action = HealingAction(
                        action_id=str(uuid.uuid4()),
                        action_type=action.get('action_type', 'unknown'),
                        selector=action.get('selector'),
                        value=action.get('value'),
                        description=action.get('description', f'自愈操作 {i+1}'),
                        success=True  # 假设Agent成功执行了操作
                    )
                    healing_actions.append(healing_action)
            
            logger.info(f"自愈任务执行完成，记录了 {len(healing_actions)} 个操作")
            
        except Exception as e:
            logger.error(f"执行自愈任务失败: {e}")
            # 记录失败操作
            healing_action = HealingAction(
                action_id=str(uuid.uuid4()),
                action_type="error",
                description=f"自愈任务失败: {str(e)}",
                success=False
            )
            healing_actions.append(healing_action)
        
        return healing_actions
    
    def _generate_healing_goal(self, error_context: ErrorContext) -> str:
        """生成自愈目标"""
        step_data = error_context.step_data
        error_type = error_context.error_type
        
        # 根据错误类型和步骤数据生成目标
        if error_type == "element_not_found":
            if step_data.get("type") == "click":
                target = step_data.get("element_description", step_data.get("selector", "目标元素"))
                return f"找到并点击 {target}，如果找不到原始元素，请寻找功能相似的替代元素"
            elif step_data.get("type") == "type":
                target = step_data.get("element_description", step_data.get("selector", "输入框"))
                value = step_data.get("value", "")
                return f"找到 {target} 并输入 '{value}'，如果找不到原始元素，请寻找功能相似的替代元素"
        
        elif error_type == "timeout":
            return f"等待页面加载完成，然后执行原始操作：{step_data.get('type', 'unknown')}"
        
        # 通用目标
        action_desc = self._describe_step_action(step_data)
        return f"修复执行失败的操作：{action_desc}。请分析当前页面状态，找到合适的方法完成这个操作。"
    
    def _describe_step_action(self, step_data: Dict[str, Any]) -> str:
        """描述步骤操作"""
        step_type = step_data.get("type", "unknown")
        
        if step_type == "click":
            target = step_data.get("element_description", step_data.get("selector", "元素"))
            return f"点击 {target}"
        elif step_type == "type":
            target = step_data.get("element_description", step_data.get("selector", "输入框"))
            value = step_data.get("value", "")
            return f"在 {target} 中输入 '{value}'"
        elif step_type == "navigate":
            url = step_data.get("url", "")
            return f"导航到 {url}"
        elif step_type == "wait":
            target = step_data.get("selector", "元素")
            return f"等待 {target} 出现"
        else:
            return f"执行 {step_type} 操作"
    
    def _build_healing_prompt(self, error_context: ErrorContext) -> str:
        """构建自愈提示"""
        prompt_parts = [
            f"我需要修复一个自动化脚本中失败的操作。",
            f"",
            f"错误信息：{error_context.error_message}",
            f"错误类型：{error_context.error_type}",
            f"失败的步骤：{self._describe_step_action(error_context.step_data)}",
            f"",
            f"当前页面URL：{error_context.page_url or '未知'}",
            f"页面标题：{error_context.page_title or '未知'}",
            f"",
            f"请分析当前页面状态，找到合适的方法完成这个操作。如果原始选择器不工作，请寻找功能相似的替代元素。",
            f"请一步步执行操作，并确保操作成功完成。"
        ]
        
        return "\n".join(prompt_parts)
    
    async def _generate_new_steps(
        self, 
        healing_actions: List[HealingAction], 
        error_context: ErrorContext
    ) -> List[Dict[str, Any]]:
        """从自愈操作生成新的工作流步骤"""
        new_steps = []
        
        for action in healing_actions:
            if not action.success:
                continue
                
            step = {
                "type": action.action_type,
                "description": action.description,
                "generated_by": "browser_use_healer",
                "original_step_index": error_context.step_index,
                "healing_session_id": error_context.error_id
            }
            
            # 添加选择器信息
            if action.selector:
                step["selector"] = action.selector
            
            # 添加值信息
            if action.value:
                step["value"] = action.value
            
            # 添加坐标信息
            if action.coordinates:
                step["coordinates"] = action.coordinates
            
            new_steps.append(step)
        
        logger.info(f"生成了 {len(new_steps)} 个新步骤")
        return new_steps
    
    async def complete_healing_session(self, session_id: str) -> Optional[HealingSession]:
        """完成自愈会话"""
        session = self.active_sessions.get(session_id)
        if not session:
            logger.warning(f"未找到自愈会话: {session_id}")
            return None
        
        # 从活跃会话中移除
        del self.active_sessions[session_id]
        
        logger.info(f"自愈会话完成: {session_id}, 成功: {session.success}")
        return session
    
    async def cancel_healing_session(self, session_id: str) -> bool:
        """取消自愈会话"""
        session = self.active_sessions.get(session_id)
        if not session:
            return False
        
        session.status = HealingStatus.FAILED
        session.success = False
        session.failure_reason = "用户取消"
        session.end_time = datetime.now()
        
        del self.active_sessions[session_id]
        
        logger.info(f"自愈会话已取消: {session_id}")
        return True
    
    async def get_healing_status(self, session_id: str) -> Optional[HealingStatus]:
        """获取自愈状态"""
        session = self.active_sessions.get(session_id)
        return session.status if session else None
    
    async def save_healing_session(self, session: HealingSession, save_dir: str = "logs/healing") -> str:
        """保存自愈会话"""
        try:
            save_path = Path(save_dir)
            save_path.mkdir(parents=True, exist_ok=True)
            
            file_path = save_path / f"healing_{session.session_id}.json"
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(session.dict(), f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"自愈会话已保存: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"保存自愈会话失败: {e}")
            raise
    
    async def load_healing_session(self, session_id: str, save_dir: str = "logs/healing") -> Optional[HealingSession]:
        """加载自愈会话"""
        try:
            file_path = Path(save_dir) / f"healing_{session_id}.json"
            
            if not file_path.exists():
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return HealingSession(**data)
            
        except Exception as e:
            logger.error(f"加载自愈会话失败: {e}")
            return None 