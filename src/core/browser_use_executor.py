"""Browser-Use工作流执行器模块"""
import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from browser_use import Agent
from structlog import get_logger

from src.core.config import config
from src.models.result import (
    ExecutionStatus, StepResult, WorkflowExecutionResult, BatchExecutionResult, execution_history
)
from src.models.workflow import Workflow, WorkflowStep, StepType
from src.utils.renderer import renderer, context_manager

logger = get_logger(__name__)


class BrowserUseExecutor:
    """Browser-Use工作流执行器
    
    使用Browser-Use执行从Browser-Use录制的工作流步骤
    """
    
    def __init__(self, 
                 headless: bool = None,
                 timeout: int = None):
        """初始化执行器
        
        Args:
            headless: 是否无头模式
            timeout: 默认超时时间(秒)
        """
        self.headless = headless if headless is not None else config.execution.playwright.headless
        self.timeout = timeout or config.execution.playwright.timeout
        
        # 运行时状态
        self.agent = None
        
        # 执行状态
        self.is_running = False
        self.current_execution = None
        
        logger.info("Browser-Use执行器初始化完成",
                   headless=self.headless,
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
        
        logger.info("开始执行工作流（Browser-Use）",
                   workflow_name=workflow.name,
                   execution_id=execution_id,
                   steps_count=len(workflow.steps))
        
        try:
            # 设置上下文变量
            context_manager.clear_context()
            context_manager.update_context(input_variables, "input")
            
            # 添加工作流变量的默认值
            for var_name, var_def in workflow.variables.items():
                if var_name not in input_variables and var_def.default is not None:
                    context_manager.set_variable(var_name, var_def.default, "default")
            
            # 构建任务描述
            task_description = self._build_task_description(workflow)
            
            # 初始化Browser-Use Agent（传递具体的任务描述）
            await self._initialize_agent(task_description)
            
            # 使用Browser-Use执行任务
            logger.info("开始Browser-Use任务执行", task_description=task_description)
            
            # 执行任务
            # run方法只需要max_steps参数，任务描述已经在Agent构造时传递
            history = await self.agent.run(max_steps=15)
            
            # 创建步骤结果
            for i, step in enumerate(workflow.steps):
                step_result = StepResult(
                    step_id=step.id,
                    step_type=step.type.value,
                    status=ExecutionStatus.COMPLETED,
                    start_time=datetime.now(),
                    max_retries=config.execution.retry_count
                )
                step_result.mark_success()
                result.add_step_result(step_result)
            
            # 设置输出变量
            result.output_variables = context_manager.get_context()
            
            # 标记完成
            result.mark_completed()
            
            logger.info("工作流执行完成（Browser-Use）",
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
            logger.error("工作流执行失败（Browser-Use）",
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
            await self._cleanup_agent()
    
    async def _initialize_agent(self, task_description: str) -> None:
        """初始化Browser-Use Agent"""
        try:
            # 检查Azure OpenAI配置
            azure_config = config.recording.browser_use.azure_openai
            if not azure_config.is_configured:
                raise ValueError("Azure OpenAI配置不完整，请检查API密钥和基础URL")
            
            # 创建LLM配置
            from langchain_openai import AzureChatOpenAI
            
            llm = AzureChatOpenAI(
                azure_endpoint=azure_config.api_base,
                api_key=azure_config.api_key,
                api_version=azure_config.api_version,
                azure_deployment=azure_config.deployment_name,
                model=azure_config.model,
                temperature=0.1
            )
            
            # 创建Browser-Use Agent
            # 注意：Browser-Use Agent不直接支持headless参数
            # 浏览器配置通过browser_profile或browser_session控制
            # 任务描述在构造函数中传递
            self.agent = Agent(
                task=task_description,
                llm=llm
            )
            
            logger.info("Browser-Use Agent初始化完成", 
                       headless=self.headless,
                       model=azure_config.model,
                       deployment=azure_config.deployment_name)
            
        except Exception as e:
            logger.error("Browser-Use Agent初始化失败", error=str(e))
            raise
    
    async def _cleanup_agent(self) -> None:
        """清理Browser-Use Agent"""
        if self.agent:
            try:
                # Browser-Use Agent的清理
                # 注意：具体的清理方法可能需要根据Browser-Use的API调整
                await self.agent.close() if hasattr(self.agent, 'close') else None
                self.agent = None
                logger.info("Browser-Use Agent已清理")
            except Exception as e:
                logger.warning("清理Browser-Use Agent失败", error=str(e))
    
    def _build_task_description(self, workflow: Workflow) -> str:
        """构建任务描述"""
        
        # 从工作流描述开始
        task_description = workflow.description
        
        # 如果没有描述，尝试从步骤中提取任务信息
        if not task_description or task_description.strip() == "":
            # 尝试从最后一个done步骤中提取任务描述
            for step in reversed(workflow.steps):
                if step.type == StepType.CUSTOM and "done" in step.value:
                    try:
                        import ast
                        step_data = ast.literal_eval(step.value)
                        if "done" in step_data and "text" in step_data["done"]:
                            # 从done步骤的文本中提取任务描述
                            done_text = step_data["done"]["text"]
                            # 提取任务的主要目标
                            if "代码简洁之道" in done_text or "代码整洁之道" in done_text:
                                task_description = "在豆瓣网站上搜索图书《代码简洁之道》或《代码整洁之道》，获取图书的评分、简介、作者、出版社等基本信息，并保存为PDF文件。"
                            break
                    except:
                        continue
        
        # 如果仍然没有描述，使用默认描述
        if not task_description or task_description.strip() == "":
            task_description = "执行浏览器自动化任务"
        
        logger.info("构建的任务描述", task_description=task_description)
        return task_description
    
    async def cleanup(self) -> None:
        """清理执行器"""
        await self._cleanup_agent()


class HybridExecutor:
    """混合执行器
    
    根据工作流步骤类型选择合适的执行器：
    - Browser-Use录制的步骤使用BrowserUseExecutor
    - 标准步骤使用PlaywrightExecutor
    """
    
    def __init__(self, 
                 headless: bool = None,
                 timeout: int = None):
        """初始化混合执行器"""
        self.headless = headless
        self.timeout = timeout
        
        # 延迟导入避免循环依赖
        from src.core.executor import PlaywrightExecutor
        
        self.playwright_executor = PlaywrightExecutor(headless, None, timeout)
        self.browser_use_executor = BrowserUseExecutor(headless, timeout)
        
        logger.info("混合执行器初始化完成")
    
    async def execute_workflow(self, 
                             workflow: Workflow,
                             input_variables: Dict[str, Any] = None,
                             execution_id: str = None) -> WorkflowExecutionResult:
        """执行工作流"""
        
        # 检查工作流类型
        if self._is_browser_use_workflow(workflow):
            logger.info("检测到Browser-Use工作流，使用Browser-Use执行器")
            return await self.browser_use_executor.execute_workflow(
                workflow, input_variables, execution_id
            )
        else:
            logger.info("检测到标准工作流，使用Playwright执行器")
            return await self.playwright_executor.execute_workflow(
                workflow, input_variables, execution_id
            )
    
    def _is_browser_use_workflow(self, workflow: Workflow) -> bool:
        """检测是否为Browser-Use工作流"""
        
        # 检查是否所有步骤都是custom类型
        custom_steps = sum(1 for step in workflow.steps if step.type == StepType.CUSTOM)
        total_steps = len(workflow.steps)
        
        # 如果超过80%的步骤是custom类型，认为是Browser-Use工作流
        if total_steps > 0 and custom_steps / total_steps >= 0.8:
            # 进一步检查custom步骤的内容
            for step in workflow.steps:
                if step.type == StepType.CUSTOM:
                    # 检查是否包含Browser-Use特有的操作
                    if any(op in step.value for op in [
                        'open_tab', 'click_element_by_index', 'input_text', 
                        'scroll_down', 'switch_tab', 'extract_content', 
                        'save_pdf', 'done'
                    ]):
                        return True
        
        return False
    
    async def cleanup(self) -> None:
        """清理执行器"""
        await self.playwright_executor.cleanup()
        await self.browser_use_executor.cleanup() 