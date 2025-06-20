"""工作流执行器模块"""
import asyncio
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from structlog import get_logger

from src.core.config import config
from src.models.result import (
    ExecutionStatus, StepResult, WorkflowExecutionResult, BatchExecutionResult, execution_history
)
from src.models.workflow import Workflow, WorkflowStep, StepType
from src.utils.renderer import renderer, context_manager
from src.core.error_detector import ErrorDetector
from src.core.browser_use_healer import BrowserUseHealer
from src.core.workflow_updater import WorkflowUpdater
from src.models.error import HealingStatus

logger = get_logger(__name__)


class PlaywrightExecutor:
    """Playwright工作流执行器
    
    使用Playwright执行工作流步骤，支持Chrome Profile复用和并发执行
    """
    
    def __init__(self, 
                 headless: bool = None,
                 user_data_dir: str = None,
                 timeout: int = None,
                 enable_healing: bool = True):
        """初始化执行器
        
        Args:
            headless: 是否无头模式
            user_data_dir: 用户数据目录
            timeout: 默认超时时间(秒)
            enable_healing: 是否启用自愈功能
        """
        self.headless = headless if headless is not None else config.execution.playwright.headless
        self.user_data_dir = user_data_dir or config.execution.playwright.user_data_dir
        self.timeout = (timeout or config.execution.playwright.timeout) * 1000  # 转换为毫秒
        self.enable_healing = enable_healing
        
        # 运行时状态
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        
        # 执行状态
        self.is_running = False
        self.current_execution = None
        
        # 自愈组件
        if self.enable_healing:
            self.error_detector = ErrorDetector()
            self.healer = BrowserUseHealer()
            self.workflow_updater = WorkflowUpdater()
        else:
            self.error_detector = None
            self.healer = None
            self.workflow_updater = None
        
        logger.info("Playwright执行器初始化完成",
                   headless=self.headless,
                   user_data_dir=self.user_data_dir,
                   timeout=self.timeout)
    
    async def execute_workflow(self, 
                             workflow: Workflow,
                             input_variables: Dict[str, Any] = None,
                             execution_id: str = None) -> WorkflowExecutionResult:
        """执行工作流
        
        Args:
            workflow: 工作流对象
            input_variables: 输入变量
            execution_id: 执行ID
            
        Returns:
            执行结果
        """
        execution_id = execution_id or f"exec_{uuid.uuid4().hex[:8]}"
        input_variables = input_variables or {}
        
        # 创建执行结果对象
        result = WorkflowExecutionResult(
            workflow_name=workflow.name,
            execution_id=execution_id,
            status=ExecutionStatus.RUNNING,
            input_variables=input_variables,
            total_steps=len(workflow.steps)
        )
        
        self.current_execution = result
        self.is_running = True
        
        logger.info("开始执行工作流",
                   workflow_name=workflow.name,
                   execution_id=execution_id,
                   steps_count=len(workflow.steps))
        
        try:
            # 初始化浏览器环境
            await self._initialize_browser()
            
            # 设置上下文变量
            context_manager.clear_context()
            context_manager.update_context(input_variables, "input")
            
            # 添加工作流变量的默认值
            for var_name, var_def in workflow.variables.items():
                if var_name not in input_variables and var_def.default is not None:
                    context_manager.set_variable(var_name, var_def.default, "default")
            
            # 执行步骤
            for i, step in enumerate(workflow.steps):
                if not self.is_running:
                    logger.info("执行被中断")
                    break
                
                step_result = await self._execute_step(step, i + 1)
                result.add_step_result(step_result)
                
                # 如果步骤失败且不允许继续，停止执行
                if not step_result.is_successful:
                    result.failed_step_id = step.id
                    result.error_message = step_result.error_message
                    break
            
            # 设置输出变量
            result.output_variables = context_manager.get_context()
            
            # 标记完成
            result.mark_completed()
            
            logger.info("工作流执行完成",
                       workflow_name=workflow.name,
                       execution_id=execution_id,
                       status=result.status.value,
                       success_rate=result.success_rate)
            
            # 保存执行历史
            try:
                execution_history.save_execution_result(result)
                logger.info("执行历史已保存", execution_id=execution_id)
            except Exception as e:
                logger.warning("保存执行历史失败", error=str(e))
            
            return result
            
        except Exception as e:
            logger.error("工作流执行失败",
                        workflow_name=workflow.name,
                        execution_id=execution_id,
                        error=str(e),
                        exc_info=True)
            
            result.status = ExecutionStatus.FAILED
            result.error_message = str(e)
            result.mark_completed()
            
            # 保存执行历史（即使失败也要保存）
            try:
                execution_history.save_execution_result(result)
                logger.info("执行历史已保存（失败）", execution_id=execution_id)
            except Exception as save_error:
                logger.warning("保存执行历史失败", error=str(save_error))
            
            return result
            
        finally:
            self.is_running = False
            self.current_execution = None
            await self._cleanup_browser()
    
    async def execute_batch(self,
                          workflow: Workflow,
                          input_data_list: List[Dict[str, Any]],
                          concurrent_limit: int = None,
                          batch_id: str = None) -> BatchExecutionResult:
        """批量执行工作流
        
        Args:
            workflow: 工作流对象
            input_data_list: 输入数据列表
            concurrent_limit: 并发限制
            batch_id: 批次ID
            
        Returns:
            批量执行结果
        """
        batch_id = batch_id or f"batch_{uuid.uuid4().hex[:8]}"
        concurrent_limit = concurrent_limit or config.execution.concurrent_limit
        
        # 创建批量执行结果对象
        batch_result = BatchExecutionResult(
            batch_id=batch_id,
            workflow_name=workflow.name,
            status=ExecutionStatus.RUNNING,
            total_executions=len(input_data_list),
            concurrent_limit=concurrent_limit,
            input_data_list=input_data_list
        )
        
        logger.info("开始批量执行工作流",
                   workflow_name=workflow.name,
                   batch_id=batch_id,
                   total_executions=len(input_data_list),
                   concurrent_limit=concurrent_limit)
        
        try:
            # 创建信号量控制并发数
            semaphore = asyncio.Semaphore(concurrent_limit)
            
            # 创建执行任务
            tasks = []
            for i, input_data in enumerate(input_data_list):
                task = self._execute_single_task(
                    workflow, input_data, semaphore, f"{batch_id}_{i}"
                )
                tasks.append(task)
            
            # 并发执行所有任务
            execution_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理执行结果
            for i, result in enumerate(execution_results):
                if isinstance(result, Exception):
                    # 创建失败的执行结果
                    failed_result = WorkflowExecutionResult(
                        workflow_name=workflow.name,
                        execution_id=f"{batch_id}_{i}",
                        status=ExecutionStatus.FAILED,
                        input_variables=input_data_list[i],
                        error_message=str(result)
                    )
                    failed_result.mark_completed()
                    batch_result.add_execution_result(failed_result)
                else:
                    batch_result.add_execution_result(result)
            
            # 标记批次完成
            batch_result.mark_completed()
            
            logger.info("批量执行完成",
                       workflow_name=workflow.name,
                       batch_id=batch_id,
                       success_rate=batch_result.success_rate,
                       total_executions=batch_result.total_executions)
            
            return batch_result
            
        except Exception as e:
            logger.error("批量执行失败",
                        workflow_name=workflow.name,
                        batch_id=batch_id,
                        error=str(e),
                        exc_info=True)
            
            batch_result.status = ExecutionStatus.FAILED
            batch_result.mark_completed()
            
            return batch_result
    
    async def _execute_single_task(self,
                                 workflow: Workflow,
                                 input_data: Dict[str, Any],
                                 semaphore: asyncio.Semaphore,
                                 execution_id: str) -> WorkflowExecutionResult:
        """执行单个任务（用于批量执行）"""
        async with semaphore:
            # 为每个任务创建独立的执行器实例
            executor = PlaywrightExecutor(
                headless=self.headless,
                user_data_dir=self.user_data_dir,
                timeout=self.timeout // 1000  # 转换回秒
            )
            
            try:
                return await executor.execute_workflow(
                    workflow, input_data, execution_id
                )
            finally:
                await executor.cleanup()
    
    async def _execute_step(self, step: WorkflowStep, step_number: int) -> StepResult:
        """执行单个步骤（集成自愈功能）
        
        Args:
            step: 工作流步骤
            step_number: 步骤序号
            
        Returns:
            步骤执行结果
        """
        step_result = StepResult(
            step_id=step.id,
            step_type=step.type.value,
            status=ExecutionStatus.RUNNING,
            start_time=datetime.now(),
            max_retries=config.execution.retry_count
        )
        
        logger.info("开始执行步骤",
                   step_id=step.id,
                   step_type=step.type.value,
                   step_number=step_number,
                   description=step.description,
                   selector=step.selector,
                   xpath=step.xpath,
                   url=step.url,
                   value=step.value,
                   key=getattr(step, 'key', None))
        
        # 设置步骤级别的超时（如果指定）
        step_timeout = getattr(step, 'timeout', None)
        if step_timeout and step_timeout > 0:
            timeout_ms = step_timeout
        else:
            timeout_ms = self.timeout
        
        # 创建超时任务
        timeout_task = None
        execution_task = None
        
        try:
            # 渲染步骤（替换变量）
            context = context_manager.get_context()
            rendered_step_data = renderer.render_workflow_step(step.model_dump(), context)
            
            # 创建执行任务
            execution_task = asyncio.create_task(
                self._execute_step_operation(step, rendered_step_data, step_result)
            )
            
            # 创建超时任务
            timeout_task = asyncio.create_task(
                self._step_timeout_handler(step.id, timeout_ms / 1000)
            )
            
            # 等待执行完成或超时
            done, pending = await asyncio.wait(
                [execution_task, timeout_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # 取消挂起的任务
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            # 检查结果
            if execution_task in done:
                # 正常完成
                if step_result.status == ExecutionStatus.RUNNING:
                    step_result.mark_success()
                
                logger.info("步骤执行成功",
                           step_id=step.id,
                           step_type=step.type.value,
                           duration=step_result.duration,
                           result_data=step_result.result_data)
            else:
                # 超时
                raise asyncio.TimeoutError(f"步骤执行超时，超过{timeout_ms/1000}秒")
            
        except Exception as e:
            logger.error("步骤执行失败",
                        step_id=step.id,
                        step_type=step.type.value,
                        error=str(e),
                        exc_info=True)
            
            # 尝试自愈
            healing_attempted = False
            if self.enable_healing and self.error_detector and self.healer:
                healing_attempted = await self._attempt_healing(
                    error=e,
                    step=step,
                    step_index=step_number - 1,
                    rendered_step_data=rendered_step_data,
                    step_result=step_result
                )
            
            # 如果自愈失败或未启用自愈，标记步骤失败
            if not healing_attempted or step_result.status != ExecutionStatus.COMPLETED:
                step_result.mark_failed(
                    error_message=str(e),
                    error_type=type(e).__name__,
                    stack_trace=str(e)
                )
        
        finally:
            # 清理任务
            if timeout_task and not timeout_task.done():
                timeout_task.cancel()
            if execution_task and not execution_task.done():
                execution_task.cancel()
        
        return step_result
    
    async def _step_timeout_handler(self, step_id: str, timeout_seconds: float):
        """步骤超时处理器"""
        await asyncio.sleep(timeout_seconds)
        logger.warning(f"步骤超时: {step_id}, 超时时间: {timeout_seconds}秒")
    
    async def _execute_step_operation(self, step: WorkflowStep, rendered_step_data: Dict[str, Any], step_result: StepResult) -> None:
        """执行具体的步骤操作"""
        try:
            # 根据步骤类型执行相应操作
            if step.type == StepType.NAVIGATE:
                await self._execute_navigate(rendered_step_data, step_result)
            elif step.type == StepType.CLICK:
                await self._execute_click(rendered_step_data, step_result)
            elif step.type == StepType.FILL:
                await self._execute_fill(rendered_step_data, step_result)
            elif step.type == StepType.SELECT:
                await self._execute_select(rendered_step_data, step_result)
            elif step.type == StepType.WAIT:
                await self._execute_wait(rendered_step_data, step_result)
            elif step.type == StepType.SCROLL:
                await self._execute_scroll(rendered_step_data, step_result)
            elif step.type == StepType.HOVER:
                await self._execute_hover(rendered_step_data, step_result)
            elif step.type == StepType.PRESS_KEY:
                await self._execute_press_key(rendered_step_data, step_result)
            elif step.type == StepType.SCREENSHOT:
                await self._execute_screenshot(rendered_step_data, step_result)
            elif step.type == StepType.EXTRACT:
                await self._execute_extract(rendered_step_data, step_result)
            elif step.type == StepType.CUSTOM:
                await self._execute_custom(rendered_step_data, step_result)
            else:
                raise ValueError(f"不支持的步骤类型: {step.type}")
        except Exception as e:
            # 确保异常被正确传播
            logger.error(f"步骤操作执行失败: {step.id}", error=str(e))
            raise
    
    async def _attempt_healing(
        self,
        error: Exception,
        step: WorkflowStep,
        step_index: int,
        rendered_step_data: Dict[str, Any],
        step_result: StepResult
    ) -> bool:
        """尝试自愈失败的步骤
        
        Args:
            error: 发生的错误
            step: 失败的步骤
            step_index: 步骤索引
            rendered_step_data: 渲染后的步骤数据
            step_result: 步骤结果对象
            
        Returns:
            是否成功自愈
        """
        try:
            logger.info("开始尝试自愈", step_id=step.id, error=str(error))
            
            # 1. 捕获错误上下文
            error_context = await self.error_detector.capture_error_context(
                error=error,
                step=rendered_step_data,
                step_index=step_index,
                workflow_path=getattr(self.current_execution, 'workflow_name', 'unknown'),
                page=self.page,
                execution_context=context_manager.get_context()
            )
            
            logger.info(f"错误上下文捕获完成: {error_context.error_id}, 类型: {error_context.error_type}, 可自愈: {error_context.is_healable}")
            
            # 2. 检查是否可自愈
            if not error_context.is_healable:
                logger.info("错误不可自愈，跳过自愈尝试", error_type=error_context.error_type)
                return False
            
            # 3. 启动自愈会话
            healing_session = await self.healer.start_healing_session(error_context)
            logger.info(f"自愈会话创建成功: {healing_session.session_id}, 目标: {healing_session.healing_goal}")
            
            # 4. 尝试Browser-Use自愈
            healing_success = await self._try_browser_use_healing(
                healing_session, error_context, rendered_step_data, step_result
            )
            
            if healing_success:
                logger.info("Browser-Use自愈成功", session_id=healing_session.session_id)
                
                # 5. 更新工作流步骤（替换失败的步骤）
                if healing_session.new_steps:
                    await self._replace_failed_step_with_healed_steps(
                        step_index, healing_session.new_steps
                    )
                    logger.info(f"已替换失败步骤，新步骤数: {len(healing_session.new_steps)}")
                
                step_result.mark_success()
                step_result.result_data = step_result.result_data or {}
                step_result.result_data["healing_applied"] = True
                step_result.result_data["healing_session_id"] = healing_session.session_id
                step_result.result_data["new_steps_count"] = len(healing_session.new_steps or [])
                return True
            else:
                # 6. 尝试简单自愈策略
                logger.info("Browser-Use自愈失败，尝试简单自愈策略")
                simple_healing_success = await self._simple_healing_strategy(
                    error_context, healing_session, rendered_step_data, step_result
                )
                
                if simple_healing_success:
                    logger.info("简单自愈策略成功", session_id=healing_session.session_id)
                    step_result.mark_success()
                    step_result.result_data = step_result.result_data or {}
                    step_result.result_data["healing_applied"] = True
                    step_result.result_data["healing_type"] = "simple"
                    return True
                else:
                    logger.warning("所有自愈策略都失败", session_id=healing_session.session_id)
                    return False
                
        except Exception as healing_error:
            logger.error("自愈过程出错", error=str(healing_error), exc_info=True)
            return False
    
    async def _try_browser_use_healing(
        self,
        healing_session,
        error_context,
        rendered_step_data: Dict[str, Any],
        step_result: StepResult
    ) -> bool:
        """尝试Browser-Use自愈"""
        try:
            # 检查是否有Browser-Use环境
            try:
                from browser_use import Agent, Browser
                from browser_use.browser.browser import BrowserConfig
                logger.info("Browser-Use环境可用，开始自愈")
            except ImportError:
                logger.warning("Browser-Use未安装，跳过Browser-Use自愈")
                return False
            
            # 使用Browser-Use进行自愈
            healing_success = await self.healer.heal_with_browser_use(healing_session)
            
            if healing_success and healing_session.new_steps:
                logger.info(f"Browser-Use自愈成功，生成了{len(healing_session.new_steps)}个新步骤")
                return True
            else:
                logger.warning("Browser-Use自愈失败或未生成新步骤")
                return False
            
        except Exception as e:
            logger.error(f"Browser-Use自愈过程出错: {e}")
            return False
    
    async def _replace_failed_step_with_healed_steps(
        self,
        failed_step_index: int,
        new_steps: List[Dict[str, Any]]
    ):
        """替换失败的步骤为自愈生成的新步骤"""
        try:
            if not self.current_execution or not hasattr(self.current_execution, 'workflow'):
                logger.warning("无法替换步骤：缺少执行上下文")
                return
            
            # 获取当前工作流
            workflow_name = self.current_execution.workflow_name
            
            # 使用工作流更新器来替换步骤
            if self.workflow_updater:
                updated_workflow = await self.workflow_updater.replace_step_with_healed_steps(
                    workflow_name=workflow_name,
                    failed_step_index=failed_step_index,
                    healed_steps=new_steps
                )
                
                if updated_workflow:
                    logger.info(f"工作流步骤替换成功: {workflow_name}")
                    # 这里可以选择是否保存更新后的工作流
                    # await self.workflow_updater.save_updated_workflow(updated_workflow)
                else:
                    logger.warning("工作流步骤替换失败")
            else:
                logger.warning("工作流更新器未初始化")
                
        except Exception as e:
            logger.error(f"替换步骤时出错: {e}")
    
    async def _simple_healing_strategy(
        self,
        error_context,
        healing_session,
        rendered_step_data: Dict[str, Any],
        step_result: StepResult
    ) -> bool:
        """简单的自愈策略（不依赖Browser-Use）"""
        try:
            error_type = error_context.error_type
            step_type = rendered_step_data.get("type")
            
            logger.info(f"开始简单自愈策略: 错误类型={error_type}, 步骤类型={step_type}")
            
            # 超时错误的自愈策略
            if "timeout" in str(error_type).lower():
                logger.info("超时错误，尝试增加等待时间")
                
                # 等待页面稳定
                await asyncio.sleep(3)
                
                # 检查页面是否仍然可用
                if self.page:
                    try:
                        current_url = self.page.url
                        logger.info(f"当前页面URL: {current_url}")
                        
                        # 如果是导航超时，尝试重新导航
                        if step_type == "navigate":
                            url = rendered_step_data.get("url")
                            if url:
                                logger.info(f"重新导航到: {url}")
                                await self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
                                step_result.result_data = {"url": url, "final_url": self.page.url}
                                return True
                        
                        # 如果是点击或填写超时，尝试等待元素
                        elif step_type in ["click", "fill"]:
                            selector = rendered_step_data.get("selector")
                            if selector:
                                try:
                                    # 等待元素出现
                                    await self.page.wait_for_selector(selector, timeout=10000)
                                    
                                    if step_type == "click":
                                        await self.page.click(selector)
                                        step_result.result_data = {"selector": selector, "clicked": True}
                                    elif step_type == "fill":
                                        value = rendered_step_data.get("value", "")
                                        await self.page.fill(selector, str(value))
                                        step_result.result_data = {"selector": selector, "value": value, "filled": True}
                                    
                                    return True
                                except Exception as e:
                                    logger.warning(f"等待元素失败: {e}")
                        
                    except Exception as e:
                        logger.warning(f"页面检查失败: {e}")
            
            # 元素未找到错误的自愈策略
            elif "element_not_found" in str(error_type).lower() and step_type == "click":
                logger.info("元素未找到错误，尝试替代选择器")
                
                # 尝试一些常见的替代选择器
                original_selector = rendered_step_data.get("selector", "")
                alternative_selectors = self._generate_alternative_selectors(original_selector)
                
                for alt_selector in alternative_selectors:
                    try:
                        logger.info(f"尝试替代选择器: {alt_selector}")
                        
                        # 检查元素是否存在
                        element = await self.page.query_selector(alt_selector)
                        if element:
                            await self.page.click(alt_selector)
                            step_result.result_data = {"selector": alt_selector, "clicked": True, "original_selector": original_selector}
                            
                            # 记录成功的替代选择器
                            healing_session.new_steps = [{
                                "type": "click",
                                "selector": alt_selector,
                                "description": f"自愈修复的点击操作（原选择器: {original_selector}）"
                            }]
                            
                            logger.info(f"替代选择器成功: {alt_selector}")
                            return True
                    except Exception as e:
                        logger.debug(f"替代选择器失败: {alt_selector}, 错误: {e}")
                        continue
                
                logger.warning("所有替代选择器都失败")
            
            # 填写错误的自愈策略
            elif "element_not_found" in str(error_type).lower() and step_type == "fill":
                logger.info("填写元素未找到，尝试替代选择器")
                
                original_selector = rendered_step_data.get("selector", "")
                value = rendered_step_data.get("value", "")
                
                # 尝试通用的输入框选择器
                fallback_selectors = [
                    'input[type="text"]',
                    'input[type="search"]',
                    'input[name*="search"]',
                    'input[name*="query"]',
                    'input[name="q"]',
                    'textarea',
                    '[contenteditable="true"]'
                ]
                
                for selector in fallback_selectors:
                    try:
                        element = await self.page.query_selector(selector)
                        if element:
                            await self.page.fill(selector, str(value))
                            step_result.result_data = {"selector": selector, "value": value, "filled": True, "original_selector": original_selector}
                            logger.info(f"使用备用选择器成功填写: {selector}")
                            return True
                    except Exception as e:
                        logger.debug(f"备用选择器失败: {selector}, 错误: {e}")
                        continue
            
            logger.info("简单自愈策略未能解决问题")
            return False
            
        except Exception as e:
            logger.error(f"简单自愈策略执行失败: {e}")
            return False
    
    def _generate_alternative_selectors(self, original_selector: str) -> List[str]:
        """生成替代选择器"""
        alternatives = []
        
        if not original_selector:
            return alternatives
        
        # CSS选择器的常见替代方案
        if original_selector.startswith("#"):
            # ID选择器替代方案
            element_id = original_selector[1:]
            alternatives.extend([
                f'[id="{element_id}"]',
                f'*[id="{element_id}"]',
                f'[id*="{element_id}"]'
            ])
        
        elif original_selector.startswith("."):
            # 类选择器替代方案
            class_name = original_selector[1:]
            alternatives.extend([
                f'[class="{class_name}"]',
                f'[class*="{class_name}"]',
                f'*[class*="{class_name}"]'
            ])
        
        # 通用替代方案
        if "submit" in original_selector.lower():
            alternatives.extend([
                'button[type="submit"]',
                'input[type="submit"]',
                'button:contains("提交")',
                'button:contains("确定")',
                'button:contains("Submit")'
            ])
        
        if "button" in original_selector.lower():
            alternatives.extend([
                'button',
                '[role="button"]',
                'input[type="button"]'
            ])
        
        return alternatives[:5]  # 限制尝试次数
    
    async def _execute_step_operation_by_type(self, step_data: Dict[str, Any], step_result: StepResult) -> None:
        """根据步骤类型执行操作（用于自愈重试）"""
        step_type = step_data.get("type")
        
        if step_type == "navigate":
            await self._execute_navigate(step_data, step_result)
        elif step_type == "click":
            await self._execute_click(step_data, step_result)
        elif step_type == "fill":
            await self._execute_fill(step_data, step_result)
        elif step_type == "select":
            await self._execute_select(step_data, step_result)
        elif step_type == "wait":
            await self._execute_wait(step_data, step_result)
        elif step_type == "scroll":
            await self._execute_scroll(step_data, step_result)
        elif step_type == "hover":
            await self._execute_hover(step_data, step_result)
        elif step_type == "press_key":
            await self._execute_press_key(step_data, step_result)
        elif step_type == "screenshot":
            await self._execute_screenshot(step_data, step_result)
        elif step_type == "extract":
            await self._execute_extract(step_data, step_result)
        elif step_type == "custom":
            await self._execute_custom(step_data, step_result)
        else:
            raise ValueError(f"不支持的步骤类型: {step_type}")
    
    async def _initialize_browser(self) -> None:
        """初始化浏览器环境"""
        if self.playwright is None:
            self.playwright = await async_playwright().start()
            
            # 设置用户数据目录
            user_data_path = Path(self.user_data_dir)
            user_data_path.mkdir(parents=True, exist_ok=True)
            
            # 如果启用了系统Chrome配置复制，则复制重要数据
            if config.execution.playwright.use_system_chrome_profile:
                self._setup_chrome_profile(user_data_path)
                logger.info("使用复制的Chrome用户数据", user_data_dir=str(user_data_path))
            else:
                logger.info("使用独立的Chrome用户数据", user_data_dir=str(user_data_path))
            
            # 检测本地Chrome路径
            chrome_path = self._get_chrome_path()
            
            # 配置启动参数
            launch_args = [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-extensions-except',
                '--disable-plugins-discovery'
            ]
            
            # 启动浏览器 - 优先使用本地Chrome
            try:
                if chrome_path:
                    self.browser = await self.playwright.chromium.launch_persistent_context(
                        user_data_dir=str(user_data_path),
                        headless=self.headless,
                        executable_path=chrome_path,
                        args=launch_args,
                        viewport={'width': 1280, 'height': 720},
                        locale='zh-CN',
                        timezone_id='Asia/Shanghai'
                    )
                    logger.info("使用本地Chrome浏览器", chrome_path=chrome_path)
                else:
                    self.browser = await self.playwright.chromium.launch_persistent_context(
                        user_data_dir=str(user_data_path),
                        headless=self.headless,
                        args=launch_args,
                        viewport={'width': 1280, 'height': 720},
                        locale='zh-CN',
                        timezone_id='Asia/Shanghai'
                    )
                    logger.info("使用Playwright内置Chromium")
            except Exception as e:
                logger.warning("使用Chrome失败，回退到Chromium", error=str(e))
                self.browser = await self.playwright.chromium.launch_persistent_context(
                    user_data_dir=str(user_data_path),
                    headless=self.headless,
                    args=launch_args,
                    viewport={'width': 1280, 'height': 720}
                )
            
            # 创建页面
            self.page = await self.browser.new_page()
            
            # 设置默认超时
            self.page.set_default_timeout(self.timeout)
            
            # 设置用户代理，避免检测
            await self.page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            
            logger.info("浏览器环境初始化完成",
                       headless=self.headless,
                       user_data_dir=self.user_data_dir)
    
    def _get_chrome_path(self) -> Optional[str]:
        """获取本地Chrome浏览器路径"""
        import platform
        
        system = platform.system()
        
        if system == "Darwin":  # macOS
            possible_paths = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/google-chrome",
                "/usr/bin/chromium-browser",
                "/usr/bin/chromium"
            ]
        elif system == "Windows":
            possible_paths = [
                "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
                "C:\\Users\\{}\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe".format(os.getenv('USERNAME', '')),
                "C:\\Program Files\\Chromium\\Application\\chromium.exe"
            ]
        else:  # Linux
            possible_paths = [
                "/usr/bin/google-chrome-stable",
                "/usr/bin/google-chrome",
                "/usr/bin/chromium-browser",
                "/usr/bin/chromium",
                "/snap/bin/chromium"
            ]
        
        for path in possible_paths:
            if Path(path).exists():
                return path
                
        return None
    
    def _get_system_chrome_user_data_dir(self) -> Optional[str]:
        """获取系统Chrome用户数据目录"""
        import platform
        
        system = platform.system()
        
        if system == "Darwin":  # macOS
            user_home = os.path.expanduser("~")
            chrome_data_dir = f"{user_home}/Library/Application Support/Google/Chrome"
        elif system == "Windows":
            username = os.getenv('USERNAME', '')
            chrome_data_dir = f"C:\\Users\\{username}\\AppData\\Local\\Google\\Chrome\\User Data"
        else:  # Linux
            user_home = os.path.expanduser("~")
            chrome_data_dir = f"{user_home}/.config/google-chrome"
        
        if Path(chrome_data_dir).exists():
            return chrome_data_dir
        
        return None
    
    def _setup_chrome_profile(self, target_dir: Path) -> None:
        """设置Chrome用户配置文件"""
        import shutil
        
        if not config.execution.playwright.use_system_chrome_profile:
            return
        
        system_chrome_dir = self._get_system_chrome_user_data_dir()
        if not system_chrome_dir:
            logger.warning("未找到系统Chrome数据目录")
            return
        
        system_path = Path(system_chrome_dir)
        
        try:
            # 确保目标目录存在
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # 复制重要的用户数据文件（避免复制会导致冲突的文件）
            important_files = [
                "Default/Cookies",
                "Default/Local Storage",
                "Default/Session Storage", 
                "Default/Web Data",
                "Default/History",
                "Default/Bookmarks",
                "Default/Preferences",
                "Default/Login Data",
                "Local State"
            ]
            
            for file_path in important_files:
                source_file = system_path / file_path
                target_file = target_dir / file_path
                
                if source_file.exists():
                    # 确保目标目录存在
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    try:
                        if source_file.is_file():
                            shutil.copy2(source_file, target_file)
                        elif source_file.is_dir():
                            if target_file.exists():
                                shutil.rmtree(target_file)
                            shutil.copytree(source_file, target_file)
                        
                        logger.debug("复制Chrome数据文件", source=str(source_file), target=str(target_file))
                    except Exception as e:
                        logger.warning("复制Chrome数据文件失败", file=file_path, error=str(e))
            
            logger.info("Chrome用户数据复制完成", 
                       source=str(system_path), 
                       target=str(target_dir))
                       
        except Exception as e:
            logger.warning("设置Chrome配置文件失败", error=str(e))
    
    async def _cleanup_browser(self) -> None:
        """清理浏览器环境"""
        try:
            if self.page:
                await self.page.close()
                self.page = None
            
            if self.browser:
                await self.browser.close()
                self.browser = None
            
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
            
            logger.info("浏览器环境清理完成")
            
        except Exception as e:
            logger.warning("浏览器环境清理时出错", error=str(e))
    
    async def cleanup(self) -> None:
        """公共清理方法"""
        await self._cleanup_browser()
    
    # 步骤执行方法
    async def _execute_navigate(self, step_data: Dict[str, Any], result: StepResult) -> None:
        """执行导航步骤"""
        url = step_data.get('url')
        if not url:
            raise ValueError("导航步骤缺少URL")
        
        await self.page.goto(url, wait_until='domcontentloaded')
        result.result_data = {'url': url, 'final_url': self.page.url}
    
    async def _execute_click(self, step_data: Dict[str, Any], result: StepResult) -> None:
        """执行点击步骤"""
        selector = step_data.get('selector') or step_data.get('xpath')
        key = step_data.get('key')
        
        # 如果有key且没有selector，则直接按键
        if key and not selector:
            await self.page.keyboard.press(key)
            result.result_data = {'key': key, 'pressed': True}
            return
        
        # 如果有selector但没有key，则点击
        if selector and not key:
            # 等待元素可见
            if step_data.get('wait_condition') == 'visible':
                await self.page.wait_for_selector(selector, state='visible')
            
            await self.page.click(selector)
            result.result_data = {'selector': selector, 'clicked': True}
            return
        
        # 如果同时有selector和key，优先尝试按键（更稳定）
        if selector and key:
            try:
                # 先尝试按键
                await self.page.keyboard.press(key)
                result.result_data = {'key': key, 'pressed': True, 'method': 'keyboard'}
                logger.info("使用键盘操作", key=key)
            except Exception as e:
                logger.warning("键盘操作失败，尝试点击", error=str(e))
                # 如果按键失败，尝试点击
                if step_data.get('wait_condition') == 'visible':
                    await self.page.wait_for_selector(selector, state='visible')
                
                await self.page.click(selector)
                result.result_data = {'selector': selector, 'clicked': True, 'method': 'click_fallback'}
            return
        
        # 如果都没有，抛出错误
        raise ValueError("点击步骤缺少选择器或按键")
    
    async def _execute_fill(self, step_data: Dict[str, Any], result: StepResult) -> None:
        """执行填写步骤"""
        selector = step_data.get('selector') or step_data.get('xpath')
        value = step_data.get('value')
        
        if not selector:
            raise ValueError("填写步骤缺少选择器")
        if value is None:
            raise ValueError("填写步骤缺少值")
        
        await self.page.fill(selector, str(value))
        result.result_data = {'selector': selector, 'value': value, 'filled': True}
    
    async def _execute_select(self, step_data: Dict[str, Any], result: StepResult) -> None:
        """执行选择步骤"""
        selector = step_data.get('selector') or step_data.get('xpath')
        value = step_data.get('value')
        
        if not selector:
            raise ValueError("选择步骤缺少选择器")
        if not value:
            raise ValueError("选择步骤缺少值")
        
        await self.page.select_option(selector, value)
        result.result_data = {'selector': selector, 'value': value, 'selected': True}
    
    async def _execute_wait(self, step_data: Dict[str, Any], result: StepResult) -> None:
        """执行等待步骤"""
        timeout = step_data.get('timeout', 5000)
        selector = step_data.get('selector')
        condition = step_data.get('wait_condition', 'visible')
        
        if selector:
            await self.page.wait_for_selector(selector, state=condition, timeout=timeout)
            result.result_data = {'selector': selector, 'condition': condition, 'waited': True}
        else:
            await asyncio.sleep(timeout / 1000)
            result.result_data = {'timeout': timeout, 'waited': True}
    
    async def _execute_scroll(self, step_data: Dict[str, Any], result: StepResult) -> None:
        """执行滚动步骤"""
        direction = step_data.get('scroll_direction', 'down')
        amount = step_data.get('scroll_amount', 500)
        
        if direction == 'down':
            await self.page.evaluate(f'window.scrollBy(0, {amount})')
        elif direction == 'up':
            await self.page.evaluate(f'window.scrollBy(0, -{amount})')
        
        result.result_data = {'direction': direction, 'amount': amount, 'scrolled': True}
    
    async def _execute_hover(self, step_data: Dict[str, Any], result: StepResult) -> None:
        """执行悬停步骤"""
        selector = step_data.get('selector') or step_data.get('xpath')
        if not selector:
            raise ValueError("悬停步骤缺少选择器")
        
        await self.page.hover(selector)
        result.result_data = {'selector': selector, 'hovered': True}
    
    async def _execute_press_key(self, step_data: Dict[str, Any], result: StepResult) -> None:
        """执行按键步骤"""
        key = step_data.get('key')
        if not key:
            raise ValueError("按键步骤缺少按键")
        
        await self.page.keyboard.press(key)
        result.result_data = {'key': key, 'pressed': True}
    
    async def _execute_screenshot(self, step_data: Dict[str, Any], result: StepResult) -> None:
        """执行截图步骤"""
        screenshot_path = step_data.get('screenshot_path') or f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        # 确保截图目录存在
        Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
        
        await self.page.screenshot(path=screenshot_path)
        result.screenshot_path = screenshot_path
        result.result_data = {'screenshot_path': screenshot_path, 'captured': True}
    
    async def _execute_extract(self, step_data: Dict[str, Any], result: StepResult) -> None:
        """执行提取步骤"""
        selector = step_data.get('selector') or step_data.get('xpath')
        if not selector:
            raise ValueError("提取步骤缺少选择器")
        
        # 提取文本内容
        elements = await self.page.query_selector_all(selector)
        extracted_data = []
        
        for element in elements:
            text_content = await element.text_content()
            if text_content:
                extracted_data.append(text_content.strip())
        
        result.extracted_data = {'selector': selector, 'data': extracted_data}
        result.result_data = {'selector': selector, 'extracted_count': len(extracted_data)}
        
        # 将提取的数据添加到上下文中
        if extracted_data:
            context_manager.set_variable(f"extracted_{step_data.get('id', 'data')}", extracted_data, "extraction")
    
    async def _execute_custom(self, step_data: Dict[str, Any], result: StepResult) -> None:
        """执行自定义步骤"""
        from src.core.browser_use_converter import browser_use_converter
        
        # 检查是否是Browser-Use操作
        value = step_data.get('value', '')
        if value and browser_use_converter._extract_browser_use_operations(value):
            logger.info("检测到Browser-Use操作，尝试转换执行", step_data=step_data)
            
            # 尝试解析并执行Browser-Use操作
            operations = browser_use_converter._parse_browser_use_value(value)
            if operations:
                await self._execute_browser_use_operations(operations, result)
                return
        
        # 检查是否是特殊的custom操作
        if isinstance(value, str):
            try:
                import json
                action_data = json.loads(value)
                action = action_data.get('action')
                
                if action == 'switch_tab':
                    await self._handle_switch_tab(action_data, result)
                    return
                elif action == 'mark_completion':
                    await self._handle_mark_completion(action_data, result)
                    return
            except (json.JSONDecodeError, ValueError):
                pass
        
        # 默认处理
        logger.info("执行自定义步骤", step_data=step_data)
        result.result_data = {'custom': True, 'step_data': step_data}
    
    async def _execute_browser_use_operations(self, operations: Dict[str, Any], result: StepResult) -> None:
        """执行Browser-Use操作"""
        executed_operations = []
        
        for op_name, op_data in operations.items():
            if op_name == 'interacted_element':
                continue  # 跳过元数据
            
            try:
                logger.info(f"执行Browser-Use操作: {op_name}", operation_data=op_data)
                
                if op_name == 'open_tab':
                    url = op_data.get('url', 'https://www.douban.com')
                    await self.page.goto(url, wait_until='domcontentloaded')
                    executed_operations.append({'operation': op_name, 'url': url, 'success': True})
                
                elif op_name == 'input_text':
                    text = op_data.get('text', '')
                    index = op_data.get('index')
                    
                    # 根据索引推测选择器
                    if index == 10:  # 豆瓣搜索框
                        selector = 'input[name="q"], input[placeholder*="搜索"]'
                    else:
                        selector = 'input[type="text"], input[type="search"], textarea'
                    
                    await self.page.fill(selector, text)
                    executed_operations.append({'operation': op_name, 'text': text, 'selector': selector, 'success': True})
                
                elif op_name == 'click_element_by_index':
                    index = op_data.get('index')
                    
                    # 根据索引推测选择器
                    if index == 12:  # 搜索按钮
                        selector = 'input[type="submit"], button[type="submit"], .search-button'
                    elif index in [36, 39]:  # 图书链接
                        selector = '.subject-item a, .title a, .book-item a'
                    else:
                        selector = f'*:nth-child({index})'
                    
                    await self.page.click(selector)
                    executed_operations.append({'operation': op_name, 'index': index, 'selector': selector, 'success': True})
                
                elif op_name == 'scroll_down':
                    await self.page.evaluate('window.scrollBy(0, 500)')
                    executed_operations.append({'operation': op_name, 'amount': 500, 'success': True})
                
                elif op_name == 'switch_tab':
                    page_id = op_data.get('page_id', 1)
                    # 获取所有页面
                    pages = self.context.pages
                    if page_id < len(pages):
                        await pages[page_id].bring_to_front()
                        self.page = pages[page_id]  # 更新当前页面引用
                        executed_operations.append({'operation': op_name, 'page_id': page_id, 'success': True})
                    else:
                        executed_operations.append({'operation': op_name, 'page_id': page_id, 'success': False, 'error': 'Page not found'})
                
                elif op_name == 'extract_content':
                    goal = op_data.get('goal', 'Extract content')
                    
                    # 基于目标选择合适的选择器
                    if 'rating' in goal.lower():
                        selector = '[class*="rating"], [class*="score"], .rating-num, .average-rating'
                    elif 'summary' in goal.lower() or 'description' in goal.lower():
                        selector = '[class*="intro"], [class*="summary"], [class*="description"], .content'
                    else:
                        selector = 'body'
                    
                    # 提取内容
                    elements = await self.page.query_selector_all(selector)
                    extracted_data = []
                    for element in elements:
                        text = await element.text_content()
                        if text and text.strip():
                            extracted_data.append(text.strip())
                    
                    executed_operations.append({
                        'operation': op_name, 
                        'goal': goal, 
                        'selector': selector,
                        'extracted_count': len(extracted_data),
                        'success': True
                    })
                
                elif op_name == 'save_pdf':
                    # 使用截图替代PDF保存
                    screenshot_path = f'browser_use_export_{len(executed_operations)}.png'
                    await self.page.screenshot(path=screenshot_path)
                    executed_operations.append({'operation': op_name, 'screenshot_path': screenshot_path, 'success': True})
                
                elif op_name == 'done':
                    success = op_data.get('success', True)
                    message = op_data.get('text', 'Task completed')
                    executed_operations.append({'operation': op_name, 'success': success, 'message': message})
                
                else:
                    logger.warning(f"不支持的Browser-Use操作: {op_name}")
                    executed_operations.append({'operation': op_name, 'success': False, 'error': 'Unsupported operation'})
                    
            except Exception as e:
                logger.error(f"Browser-Use操作执行失败: {op_name}", error=str(e))
                executed_operations.append({'operation': op_name, 'success': False, 'error': str(e)})
        
        result.result_data = {
            'browser_use_operations': executed_operations,
            'total_operations': len(operations),
            'successful_operations': len([op for op in executed_operations if op.get('success')])
        }
    
    async def _handle_switch_tab(self, action_data: Dict[str, Any], result: StepResult) -> None:
        """处理切换标签页操作"""
        try:
            page_id = action_data.get('page_id', 1)
            pages = self.context.pages
            
            if page_id < len(pages):
                await pages[page_id].bring_to_front()
                self.page = pages[page_id]
                result.result_data = {'switch_tab': True, 'page_id': page_id, 'success': True}
                logger.info(f"切换到标签页 {page_id}")
            else:
                result.result_data = {'switch_tab': False, 'page_id': page_id, 'error': 'Page not found'}
                logger.error(f"标签页 {page_id} 不存在")
        except Exception as e:
            result.result_data = {'switch_tab': False, 'error': str(e)}
            logger.error(f"切换标签页失败: {e}")
    
    async def _handle_mark_completion(self, action_data: Dict[str, Any], result: StepResult) -> None:
        """处理标记完成操作"""
        success = action_data.get('success', True)
        message = action_data.get('message', 'Task completed')
        
        result.result_data = {
            'completion_marked': True,
            'task_success': success,
            'message': message
        }
        
        logger.info(f"任务完成标记: {'成功' if success else '失败'}", message=message)


class TaskManager:
    """任务管理器
    
    管理工作流执行任务的调度和监控
    """
    
    def __init__(self):
        """初始化任务管理器"""
        self.active_tasks = {}
        self.task_history = []
        
        logger.info("任务管理器初始化完成")
    
    async def submit_workflow_task(self,
                                 workflow: Workflow,
                                 input_variables: Dict[str, Any] = None,
                                 task_id: str = None) -> str:
        """提交工作流执行任务
        
        Args:
            workflow: 工作流对象
            input_variables: 输入变量
            task_id: 任务ID
            
        Returns:
            任务ID
        """
        task_id = task_id or f"task_{uuid.uuid4().hex[:8]}"
        
        # 创建混合执行器
        from src.core.browser_use_executor import HybridExecutor
        executor = HybridExecutor()
        
        # 创建异步任务
        task = asyncio.create_task(
            executor.execute_workflow(workflow, input_variables, task_id)
        )
        
        # 记录任务
        self.active_tasks[task_id] = {
            'task': task,
            'executor': executor,
            'workflow_name': workflow.name,
            'start_time': datetime.now(),
            'status': 'running'
        }
        
        logger.info("工作流任务已提交", task_id=task_id, workflow_name=workflow.name)
        
        return task_id
    
    async def submit_batch_task(self,
                              workflow: Workflow,
                              input_data_list: List[Dict[str, Any]],
                              concurrent_limit: int = None,
                              task_id: str = None) -> str:
        """提交批量执行任务"""
        task_id = task_id or f"batch_task_{uuid.uuid4().hex[:8]}"
        
        # 创建执行器
        executor = PlaywrightExecutor()
        
        # 创建异步任务
        task = asyncio.create_task(
            executor.execute_batch(workflow, input_data_list, concurrent_limit, task_id)
        )
        
        # 记录任务
        self.active_tasks[task_id] = {
            'task': task,
            'executor': executor,
            'workflow_name': workflow.name,
            'start_time': datetime.now(),
            'status': 'running',
            'batch_size': len(input_data_list)
        }
        
        logger.info("批量任务已提交", task_id=task_id, workflow_name=workflow.name, batch_size=len(input_data_list))
        
        return task_id
    
    async def get_task_result(self, task_id: str) -> Optional[Union[WorkflowExecutionResult, BatchExecutionResult]]:
        """获取任务结果"""
        if task_id not in self.active_tasks:
            return None
        
        task_info = self.active_tasks[task_id]
        task = task_info['task']
        
        if task.done():
            try:
                result = await task
                task_info['status'] = 'completed'
                return result
            except Exception as e:
                task_info['status'] = 'failed'
                task_info['error'] = str(e)
                logger.error("任务执行失败", task_id=task_id, error=str(e))
                return None
        
        return None
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        if task_id not in self.active_tasks:
            return False
        
        task_info = self.active_tasks[task_id]
        task = task_info['task']
        executor = task_info['executor']
        
        # 取消任务
        task.cancel()
        
        # 清理执行器
        await executor.cleanup()
        
        task_info['status'] = 'cancelled'
        
        logger.info("任务已取消", task_id=task_id)
        
        return True
    
    def get_active_tasks(self) -> Dict[str, Dict[str, Any]]:
        """获取活动任务列表"""
        return {
            task_id: {
                'workflow_name': info['workflow_name'],
                'start_time': info['start_time'],
                'status': info['status'],
                'batch_size': info.get('batch_size')
            }
            for task_id, info in self.active_tasks.items()
        }
    
    async def cleanup_completed_tasks(self) -> None:
        """清理已完成的任务"""
        completed_tasks = []
        
        for task_id, task_info in self.active_tasks.items():
            task = task_info['task']
            if task.done():
                completed_tasks.append(task_id)
                
                # 清理执行器
                executor = task_info['executor']
                await executor.cleanup()
                
                # 添加到历史记录
                self.task_history.append({
                    'task_id': task_id,
                    'workflow_name': task_info['workflow_name'],
                    'start_time': task_info['start_time'],
                    'end_time': datetime.now(),
                    'status': task_info['status']
                })
        
        # 从活动任务中移除
        for task_id in completed_tasks:
            del self.active_tasks[task_id]
        
        if completed_tasks:
            logger.info("已清理完成的任务", task_count=len(completed_tasks))


# 全局任务管理器实例
task_manager = TaskManager()
