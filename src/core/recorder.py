"""工作流录制器"""
import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from browser_use import Agent
from browser_use.browser.browser import Browser
from browser_use.browser.context import BrowserContext

# 使用绝对导入避免相对导入问题
import sys
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.core.config import config
from src.models.workflow import Workflow, WorkflowStep, WorkflowVariable, StepType
from src.utils.logger import logger

# 添加转换器导入
from .browser_use_converter import BrowserUseConverter
from .workflow_converter import WorkflowConverter


def create_azure_openai_llm():
    """创建Azure OpenAI LLM实例"""
    try:
        from langchain_openai import AzureChatOpenAI
        
        azure_config = config.recording.browser_use.azure_openai
        
        if not azure_config.is_configured:
            logger.error("Azure OpenAI配置不完整", 
                        api_key_set=bool(azure_config.api_key),
                        api_base_set=bool(azure_config.api_base))
            raise ValueError("Azure OpenAI配置不完整，请设置AZURE_OPENAI_API_KEY和AZURE_OPENAI_API_BASE环境变量")
        
        llm = AzureChatOpenAI(
            azure_endpoint=azure_config.api_base,
            api_key=azure_config.api_key,
            api_version=azure_config.api_version,
            deployment_name=azure_config.deployment_name,
            model=azure_config.model,
            temperature=0.1,
            max_tokens=4000
        )
        
        logger.info("Azure OpenAI LLM创建成功", 
                   deployment=azure_config.deployment_name,
                   model=azure_config.model)
        
        return llm
        
    except ImportError:
        logger.error("缺少langchain_openai依赖，请安装: pip install langchain-openai")
        raise
    except Exception as e:
        logger.error("创建Azure OpenAI LLM失败", error=str(e))
        raise


class WorkflowRecorder:
    """工作流录制器 - 集成Browser-Use"""
    
    def __init__(self, output_dir: Optional[str] = None):
        """初始化录制器
        
        Args:
            output_dir: 输出目录，默认使用配置中的目录
        """
        self.output_dir = Path(output_dir or config.recording.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.agent: Optional[Agent] = None
        self.playwright = None  # 添加playwright属性
        
        self.current_workflow: Optional[Workflow] = None
        self.recording_active = False
        
        # 初始化转换器
        self.browser_use_converter = BrowserUseConverter()
        self.workflow_converter = WorkflowConverter()
        
        logger.info("WorkflowRecorder初始化完成", output_dir=str(self.output_dir))
    
    async def record_with_browser_use(self, 
                                    workflow_name: str,
                                    task_description: str,
                                    headless: bool = False) -> Workflow:
        """使用Browser-Use录制工作流
        
        Args:
            workflow_name: 工作流名称
            task_description: 任务描述
            headless: 是否无头模式
            
        Returns:
            录制的工作流对象
        """
        try:
            # 创建LLM实例
            llm = create_azure_openai_llm()
            
            # 创建工作流对象
            self.current_workflow = Workflow(
                name=workflow_name,
                description=task_description,
                version="1.0.0"
            )
            
            # 使用正确的Browser-Use Agent初始化方式
            from playwright.async_api import async_playwright
            
            # 启动Playwright浏览器
            self.playwright = await async_playwright().start()
            browser = await self.playwright.chromium.launch(
                headless=headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            
            # 创建Browser-Use代理，传递正确的参数
            self.agent = Agent(
                task=task_description,
                llm=llm,
                browser=browser,  # 直接传递browser对象
                use_vision=True,
                max_failures=3,
                retry_delay=10
            )
            
            self.recording_active = True
            logger.info("开始Browser-Use录制", 
                       workflow_name=workflow_name,
                       task=task_description,
                       headless=headless)
            
            # 执行任务录制
            result = await self.agent.run()
            
            # 保存原始Browser-Use历史用于调试
            history_file = self.output_dir / f"{workflow_name}_browser_use_history.json"
            result.save_to_file(str(history_file))
            logger.info("Browser-Use历史已保存", history_file=str(history_file))
            
            # 转换Browser-Use结果为工作流步骤
            await self._convert_browser_use_result(result)
            
            # 使用Browser-Use转换器进行智能转换
            logger.info("开始Browser-Use智能转换", workflow_name=workflow_name)
            converted_workflow = self.browser_use_converter.convert_workflow(self.current_workflow)
            
            # 保存转换后的兼容工作流
            output_file = self.output_dir / f"{workflow_name}.json"
            converted_workflow.save_to_file(output_file)
            
            # 更新当前工作流为转换后的版本
            self.current_workflow = converted_workflow
            
            logger.info("Browser-Use录制完成（已转换为兼容版本）", 
                       workflow_name=workflow_name,
                       steps_count=len(self.current_workflow.steps),
                       output_file=str(output_file))
            
            return self.current_workflow
            
        except Exception as e:
            logger.error("Browser-Use录制失败", error=str(e))
            raise
        finally:
            await self.cleanup()
    
    async def _convert_browser_use_result(self, result):
        """转换Browser-Use结果为工作流步骤"""
        if not self.current_workflow:
            return
            
        try:
            logger.info("开始转换Browser-Use结果", 
                       result_type=type(result).__name__,
                       has_history=hasattr(result, 'history'),
                       steps_count=result.number_of_steps() if hasattr(result, 'number_of_steps') else 0)
            
            # Browser-Use返回AgentHistoryList对象
            if hasattr(result, 'history') and result.history:
                # 获取所有动作
                actions = result.model_actions()
                logger.info("获取到动作列表", actions_count=len(actions))
                
                for i, action in enumerate(actions):
                    await self._convert_action_to_step(action, i + 1)
                    
            # 如果没有动作，尝试从历史记录中提取
            elif hasattr(result, 'history') and result.history:
                logger.info("从历史记录中提取步骤", history_count=len(result.history))
                
                for i, history_item in enumerate(result.history):
                    # 从历史项中提取动作信息
                    if hasattr(history_item, 'model_output') and history_item.model_output:
                        await self._convert_history_item_to_step(history_item, i + 1)
                    else:
                        # 创建通用步骤
                        step = WorkflowStep(
                            id=f"step_{i+1}_{uuid.uuid4().hex[:8]}",
                            type=StepType.CUSTOM,
                            description=f"Browser-Use操作 {i+1}",
                            value=str(history_item)
                        )
                        self.current_workflow.add_step(step)
            else:
                # 如果没有详细的动作历史，创建一个通用步骤
                logger.warning("无法获取详细动作历史，创建通用步骤")
                step = WorkflowStep(
                    id=f"step_1_{uuid.uuid4().hex[:8]}",
                    type=StepType.CUSTOM,
                    description="Browser-Use执行的任务",
                    value=str(result)
                )
                self.current_workflow.add_step(step)
                
        except Exception as e:
            logger.error("转换Browser-Use结果时出错", error=str(e), exc_info=True)
            # 创建一个备用步骤
            step = WorkflowStep(
                id=f"step_fallback_{uuid.uuid4().hex[:8]}",
                type=StepType.CUSTOM,
                description="Browser-Use录制的操作",
                value="请手动编辑此步骤"
            )
            self.current_workflow.add_step(step)
    
    async def _convert_action_to_step(self, action, step_number: int):
        """将单个动作转换为工作流步骤"""
        step_id = f"step_{step_number}_{uuid.uuid4().hex[:8]}"
        
        logger.debug("转换动作", step_number=step_number, action_type=type(action), action_content=str(action))
        
        # Browser-Use的动作通常是字典格式
        if isinstance(action, dict):
            action_name = action.get('action', action.get('name', 'unknown'))
            
            if action_name == 'goto' or action_name == 'navigate':
                step = WorkflowStep(
                    id=step_id,
                    type=StepType.NAVIGATE,
                    description=f"导航到 {action.get('url', '')}",
                    url=action.get('url', ''),
                )
            elif action_name == 'click':
                step = WorkflowStep(
                    id=step_id,
                    type=StepType.CLICK,
                    description=f"点击元素: {action.get('coordinate', action.get('selector', ''))}",
                    selector=action.get('selector', ''),
                    xpath=action.get('xpath', ''),
                    value=str(action.get('coordinate', '')) if 'coordinate' in action else None,
                )
            elif action_name == 'type' or action_name == 'fill':
                step = WorkflowStep(
                    id=step_id,
                    type=StepType.FILL,
                    description=f"输入文本: {action.get('text', '')}",
                    selector=action.get('selector', ''),
                    value=action.get('text', action.get('value', '')),
                )
            elif action_name == 'wait':
                step = WorkflowStep(
                    id=step_id,
                    type=StepType.WAIT,
                    description=f"等待 {action.get('timeout', 5000)}ms",
                    timeout=action.get('timeout', 5000),
                )
            else:
                # 默认为自定义步骤
                step = WorkflowStep(
                    id=step_id,
                    type=StepType.CUSTOM,
                    description=f"{action_name}: {action.get('description', str(action))}",
                    value=str(action),
                )
        else:
            # 如果不是字典，尝试从属性获取信息
            action_type = getattr(action, 'type', getattr(action, 'action', 'unknown'))
            
            if action_type == 'navigate' or 'goto' in str(action).lower():
                step = WorkflowStep(
                    id=step_id,
                    type=StepType.NAVIGATE,
                    description=f"导航操作 {step_number}",
                    url=getattr(action, 'url', ''),
                )
            elif action_type == 'click' or 'click' in str(action).lower():
                step = WorkflowStep(
                    id=step_id,
                    type=StepType.CLICK,
                    description=f"点击操作 {step_number}",
                    selector=getattr(action, 'selector', ''),
                    xpath=getattr(action, 'xpath', ''),
                )
            elif action_type == 'type' or action_type == 'fill' or 'type' in str(action).lower():
                step = WorkflowStep(
                    id=step_id,
                    type=StepType.FILL,
                    description=f"填写操作 {step_number}",
                    selector=getattr(action, 'selector', ''),
                    value=getattr(action, 'text', getattr(action, 'value', '')),
                )
            elif action_type == 'wait' or 'wait' in str(action).lower():
                step = WorkflowStep(
                    id=step_id,
                    type=StepType.WAIT,
                    description=f"等待操作 {step_number}",
                    timeout=getattr(action, 'timeout', 5000),
                )
            else:
                # 默认为自定义步骤
                step = WorkflowStep(
                    id=step_id,
                    type=StepType.CUSTOM,
                    description=f"自定义操作 {step_number}: {action_type}",
                    value=str(action),
                )
        
        self.current_workflow.add_step(step)
        logger.info("转换动作为步骤", 
                    step_id=step_id,
                    step_type=step.type.value,
                    description=step.description)
    
    async def _convert_history_item_to_step(self, history_item, step_number: int):
        """将历史项转换为工作流步骤"""
        step_id = f"step_{step_number}_{uuid.uuid4().hex[:8]}"
        
        try:
            # 从model_output中提取动作信息
            model_output = history_item.model_output
            if hasattr(model_output, 'action') and model_output.action:
                action = model_output.action
                
                # 根据动作类型创建步骤
                if hasattr(action, 'action_name'):
                    action_name = action.action_name
                    
                    if action_name == 'goto':
                        step = WorkflowStep(
                            id=step_id,
                            type=StepType.NAVIGATE,
                            description=f"导航到页面",
                            url=getattr(action, 'url', ''),
                        )
                    elif action_name == 'click':
                        step = WorkflowStep(
                            id=step_id,
                            type=StepType.CLICK,
                            description=f"点击元素",
                            selector=getattr(action, 'selector', ''),
                            xpath=getattr(action, 'xpath', ''),
                        )
                    elif action_name == 'type':
                        step = WorkflowStep(
                            id=step_id,
                            type=StepType.FILL,
                            description=f"输入文本",
                            selector=getattr(action, 'selector', ''),
                            value=getattr(action, 'text', ''),
                        )
                    else:
                        step = WorkflowStep(
                            id=step_id,
                            type=StepType.CUSTOM,
                            description=f"{action_name}操作",
                            value=str(action),
                        )
                else:
                    # 通用步骤
                    step = WorkflowStep(
                        id=step_id,
                        type=StepType.CUSTOM,
                        description=f"Browser-Use操作 {step_number}",
                        value=str(model_output),
                    )
            else:
                # 无法提取具体动作，创建通用步骤
                step = WorkflowStep(
                    id=step_id,
                    type=StepType.CUSTOM,
                    description=f"Browser-Use操作 {step_number}",
                    value=str(history_item),
                )
                
            self.current_workflow.add_step(step)
            logger.info("从历史项转换步骤", 
                       step_id=step_id,
                       step_type=step.type.value,
                       description=step.description)
                       
        except Exception as e:
            logger.error("转换历史项时出错", error=str(e))
            # 创建备用步骤
            step = WorkflowStep(
                id=step_id,
                type=StepType.CUSTOM,
                description=f"Browser-Use操作 {step_number}",
                value="无法解析的操作"
            )
            self.current_workflow.add_step(step)

    async def start_recording(self, 
                            workflow_name: str,
                            description: str = "",
                            headless: bool = None) -> Workflow:
        """开始录制工作流
        
        Args:
            workflow_name: 工作流名称
            description: 工作流描述
            headless: 是否无头模式，默认使用配置
            
        Returns:
            创建的工作流对象
        """
        if self.recording_active:
            raise RuntimeError("录制已在进行中")
        
        # 创建工作流对象
        self.current_workflow = Workflow(
            name=workflow_name,
            description=description,
            version="1.0.0"
        )
        
        # 初始化浏览器
        headless = headless if headless is not None else config.recording.browser_use.headless
        
        try:
            # 创建Browser-Use代理
            self.agent = Agent(
                task="录制用户操作流程",
                llm=None,  # 录制模式不需要LLM
                browser_config={
                    "headless": headless,
                    "viewport": {"width": 1280, "height": 720}
                }
            )
            
            self.recording_active = True
            logger.info("开始录制工作流", 
                       workflow_name=workflow_name, 
                       headless=headless)
            
            return self.current_workflow
            
        except Exception as e:
            logger.error("启动录制失败", error=str(e))
            await self.cleanup()
            raise
    
    async def stop_recording(self, save: bool = True) -> Optional[Workflow]:
        """停止录制
        
        Args:
            save: 是否保存工作流
            
        Returns:
            录制的工作流对象
        """
        if not self.recording_active:
            logger.warning("没有正在进行的录制")
            return None
        
        try:
            workflow = self.current_workflow
            
            if save and workflow:
                # 保存工作流
                output_file = self.output_dir / f"{workflow.name}.json"
                workflow.save_to_file(output_file)
                logger.info("工作流保存完成", 
                           workflow_name=workflow.name,
                           output_file=str(output_file),
                           steps_count=len(workflow.steps))
            
            return workflow
            
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """清理资源"""
        self.recording_active = False
        
        if self.agent:
            try:
                # Browser-Use Agent可能有自己的清理方法
                if hasattr(self.agent, 'browser') and self.agent.browser:
                    await self.agent.browser.close()
            except Exception as e:
                logger.warning("关闭Browser-Use Agent时出错", error=str(e))
        
        # 关闭Playwright
        if hasattr(self, 'playwright') and self.playwright:
            try:
                await self.playwright.stop()
            except Exception as e:
                logger.warning("关闭Playwright时出错", error=str(e))
        
        self.agent = None
        self.browser = None
        self.context = None
        self.current_workflow = None
        
        logger.info("录制器资源清理完成")
    
    async def record_step(self, 
                         step_type: StepType,
                         description: str = "",
                         **kwargs) -> WorkflowStep:
        """记录单个步骤
        
        Args:
            step_type: 步骤类型
            description: 步骤描述
            **kwargs: 步骤参数
            
        Returns:
            创建的步骤对象
        """
        if not self.recording_active or not self.current_workflow:
            raise RuntimeError("录制未激活")
        
        # 生成步骤ID
        step_id = f"step_{len(self.current_workflow.steps) + 1}_{uuid.uuid4().hex[:8]}"
        
        # 创建步骤对象
        step = WorkflowStep(
            id=step_id,
            type=step_type,
            description=description,
            **kwargs
        )
        
        # 添加到工作流
        self.current_workflow.add_step(step)
        
        logger.info("记录步骤", 
                   step_id=step_id,
                   step_type=step_type.value,
                   description=description)
        
        return step
    
    async def record_navigation(self, url: str, description: str = "") -> WorkflowStep:
        """记录导航步骤"""
        return await self.record_step(
            StepType.NAVIGATE,
            description=description or f"导航到 {url}",
            url=url
        )
    
    async def record_click(self, 
                          selector: str, 
                          description: str = "",
                          xpath: str = None) -> WorkflowStep:
        """记录点击步骤"""
        return await self.record_step(
            StepType.CLICK,
            description=description or f"点击 {selector}",
            selector=selector,
            xpath=xpath
        )
    
    async def record_fill(self, 
                         selector: str, 
                         value: str,
                         description: str = "",
                         xpath: str = None) -> WorkflowStep:
        """记录填写步骤"""
        return await self.record_step(
            StepType.FILL,
            description=description or f"填写 {selector}",
            selector=selector,
            xpath=xpath,
            value=value
        )
    
    async def record_wait(self, 
                         selector: str = None,
                         timeout: int = 5000,
                         description: str = "",
                         wait_condition: str = "visible") -> WorkflowStep:
        """记录等待步骤"""
        return await self.record_step(
            StepType.WAIT,
            description=description or f"等待 {selector or '页面加载'}",
            selector=selector,
            timeout=timeout,
            wait_condition=wait_condition
        )
    
    def add_variable(self, 
                    name: str, 
                    var_type: str = "string",
                    description: str = "",
                    default: Any = None,
                    required: bool = False) -> WorkflowVariable:
        """添加工作流变量"""
        if not self.current_workflow:
            raise RuntimeError("没有活动的工作流")
        
        variable = WorkflowVariable(
            name=name,
            type=var_type,
            description=description,
            default=default,
            required=required
        )
        
        self.current_workflow.add_variable(variable)
        
        logger.info("添加工作流变量", 
                   name=name, 
                   type=var_type,
                   required=required)
        
        return variable
    
    async def interactive_recording(self, 
                                  workflow_name: str,
                                  description: str = "") -> Workflow:
        """交互式录制 - 用户手动操作，系统自动记录
        
        这是一个简化版本，实际实现需要集成Browser-Use的事件监听
        """
        workflow = await self.start_recording(workflow_name, description, headless=False)
        
        logger.info("交互式录制已启动，请在浏览器中进行操作...")
        logger.info("完成操作后，请调用 stop_recording() 方法")
        
        # 在实际实现中，这里会启动事件监听器
        # 监听用户的点击、输入、导航等操作
        # 并自动调用相应的 record_* 方法
        
        return workflow
    
    async def guided_recording(self, 
                             workflow_name: str,
                             task_description: str) -> Workflow:
        """引导式录制 - 使用Browser-Use Agent执行任务并记录
        
        Args:
            workflow_name: 工作流名称
            task_description: 任务描述
            
        Returns:
            录制的工作流
        """
        workflow = await self.start_recording(workflow_name, task_description)
        
        try:
            # 重新创建带LLM的Agent用于执行任务
            from langchain_openai import ChatOpenAI
            
            llm = ChatOpenAI(
                model=config.recording.browser_use.model,
                temperature=0
            )
            
            self.agent = Agent(
                task=task_description,
                llm=llm,
                browser_config={
                    "headless": config.recording.browser_use.headless,
                    "viewport": {"width": 1280, "height": 720}
                }
            )
            
            # 执行任务并记录步骤
            logger.info("开始引导式录制", task=task_description)
            
            # 这里需要实现Browser-Use的执行监听
            # 当Agent执行操作时，自动记录为工作流步骤
            result = await self.agent.run()
            
            logger.info("引导式录制完成", result=str(result))
            
            return workflow
            
        except Exception as e:
            logger.error("引导式录制失败", error=str(e))
            await self.cleanup()
            raise
    
    def list_workflows(self) -> List[Dict[str, Any]]:
        """列出所有已保存的工作流"""
        workflows = []
        
        for workflow_file in self.output_dir.glob("*.json"):
            try:
                workflow = Workflow.load_from_file(workflow_file)
                workflows.append({
                    "name": workflow.name,
                    "description": workflow.description,
                    "version": workflow.version,
                    "steps_count": len(workflow.steps),
                    "variables_count": len(workflow.variables),
                    "created_at": workflow.created_at,
                    "file_path": str(workflow_file)
                })
            except Exception as e:
                logger.warning(f"加载工作流失败: {workflow_file}", error=str(e))
        
        return workflows
    
    def load_workflow(self, workflow_name: str) -> Optional[Workflow]:
        """加载指定的工作流（自动转换未兼容版本）"""
        workflow_file = self.output_dir / f"{workflow_name}.json"
        
        if not workflow_file.exists():
            logger.error("工作流文件不存在", workflow_name=workflow_name)
            return None
        
        try:
            workflow = Workflow.load_from_file(workflow_file)
            
            # 检查是否需要转换
            if self.workflow_converter.needs_conversion(workflow):
                logger.info("检测到未兼容工作流，开始自动转换", workflow_name=workflow_name)
                
                # 创建备份
                backup_file = self.output_dir / f"{workflow_name}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                workflow.save_to_file(backup_file)
                logger.info("原始工作流已备份", backup_file=str(backup_file))
                
                # 执行转换
                converted_workflow = self.browser_use_converter.convert_workflow(workflow)
                
                # 保存转换后的版本
                converted_workflow.save_to_file(workflow_file)
                logger.info("工作流已转换为兼容版本并保存", workflow_name=workflow_name)
                
                return converted_workflow
            else:
                logger.info("工作流加载成功（已兼容）", workflow_name=workflow_name)
                return workflow
                
        except Exception as e:
            logger.error("工作流加载失败", workflow_name=workflow_name, error=str(e))
            return None
