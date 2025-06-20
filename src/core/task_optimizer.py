"""Browser-Use 任务优化器"""
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from langchain_openai import AzureChatOpenAI

from .config import config
from ..utils.logger import logger


@dataclass
class OptimizationResult:
    """优化结果数据类"""
    success: bool
    original_task: str
    optimized_task: str
    optimization_time: float
    improvements: List[str]
    error_message: Optional[str] = None


class TaskOptimizer:
    """Browser-Use 任务优化器
    
    负责将用户输入的任务描述优化为符合Browser-Use最佳实践的格式
    """
    
    def __init__(self):
        """初始化任务优化器"""
        self.llm: Optional[AzureChatOpenAI] = None
        self.system_prompt: str = ""
        self._load_system_prompt()
        self._initialize_llm()
    
    def _load_system_prompt(self) -> None:
        """从外部文件加载系统提示词"""
        try:
            # 获取项目根目录
            project_root = Path(__file__).parent.parent.parent
            prompt_file = project_root / "task_optimizer_prompt.txt"
            
            if prompt_file.exists():
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    self.system_prompt = f.read().strip()
                logger.info("系统提示词加载成功", prompt_file=str(prompt_file), length=len(self.system_prompt))
            else:
                # 如果文件不存在，使用默认提示词
                self.system_prompt = self._get_default_system_prompt()
                logger.warning("提示词文件不存在，使用默认提示词", prompt_file=str(prompt_file))
                
        except Exception as e:
            logger.error("加载系统提示词失败，使用默认提示词", error=str(e))
            self.system_prompt = self._get_default_system_prompt()
    
    def _get_default_system_prompt(self) -> str:
        """获取默认系统提示词（作为备用）"""
        return """你是「Browser-Use 任务优化器」，专门将用户任务转换为最佳的 Browser-Use 执行格式。

**核心目标**：将 <<USER_TASK>> 优化为单个、清晰、可执行的 Browser-Use task 描述。

**优化规则**：
1. **目标聚焦**：用一句简洁祈使句概括最终目标
2. **步骤明确**：使用编号列出关键操作，逻辑清晰、可执行
3. **输出精确**：明确文件名、格式、字段要求
4. **约束清楚**：列出域名限制、过滤条件、时间约束
5. **验证明确**：说明完成标志和错误处理方案
6. **表达精确**：避免模糊指代，使用具体值
7. **单一原则**：一次一个主目标，复杂任务需拆分说明

**Browser-Use 特性优化**：
- 优先使用可见元素选择器
- 明确等待条件和超时设置
- 指定截图和数据保存要求
- 考虑页面加载和响应时间

**输出要求**：
- 仅输出优化后的 task 字符串
- 不包含任何解释、标记或额外内容
- 使用与用户相同的语言

**质量检查**：
- 任务是否可独立执行？
- 步骤是否逻辑清晰？
- 是否包含必要的验证？
- 错误处理是否充分？

现在开始优化任务。"""
    
    def reload_system_prompt(self) -> bool:
        """重新加载系统提示词
        
        Returns:
            是否成功重新加载
        """
        try:
            old_prompt = self.system_prompt
            self._load_system_prompt()
            
            if self.system_prompt != old_prompt:
                logger.info("系统提示词已更新", 
                           old_length=len(old_prompt),
                           new_length=len(self.system_prompt))
                return True
            else:
                logger.info("系统提示词无变化")
                return False
                
        except Exception as e:
            logger.error("重新加载系统提示词失败", error=str(e))
            return False
    
    def get_system_prompt_info(self) -> Dict[str, Any]:
        """获取系统提示词信息
        
        Returns:
            包含提示词信息的字典
        """
        project_root = Path(__file__).parent.parent.parent
        prompt_file = project_root / "task_optimizer_prompt.txt"
        
        return {
            "prompt_file": str(prompt_file),
            "file_exists": prompt_file.exists(),
            "prompt_length": len(self.system_prompt),
            "last_modified": prompt_file.stat().st_mtime if prompt_file.exists() else None
        }
    
    def _initialize_llm(self) -> None:
        """初始化Azure OpenAI LLM客户端"""
        try:
            azure_config = config.recording.browser_use.azure_openai
            
            if not azure_config.is_configured:
                logger.error("Azure OpenAI配置不完整", 
                            api_key_set=bool(azure_config.api_key),
                            api_base_set=bool(azure_config.api_base))
                raise ValueError("Azure OpenAI配置不完整，请设置AZURE_OPENAI_API_KEY和AZURE_OPENAI_API_BASE环境变量")
            
            self.llm = AzureChatOpenAI(
                azure_endpoint=azure_config.api_base,
                api_key=azure_config.api_key,
                api_version=azure_config.api_version,
                deployment_name=azure_config.deployment_name,
                model=azure_config.model,
                temperature=0.1,
                max_tokens=2000,
                timeout=30.0
            )
            
            logger.info("TaskOptimizer Azure OpenAI LLM初始化成功", 
                       deployment=azure_config.deployment_name,
                       model=azure_config.model)
            
        except Exception as e:
            logger.error("TaskOptimizer Azure OpenAI LLM初始化失败", error=str(e))
            self.llm = None
            raise
    
    def _format_optimization_prompt(self, user_task: str, language: str = "zh") -> str:
        """格式化优化提示词
        
        Args:
            user_task: 用户原始任务描述
            language: 目标语言，默认中文
            
        Returns:
            格式化后的完整提示词
        """
        user_prompt = f"""请优化以下用户任务：

<<USER_TASK>>
{user_task}
<</USER_TASK>>

请按照上述规则将此任务优化为最佳的Browser-Use格式，并使用{language}语言输出结果。"""
        
        return user_prompt
    
    def _analyze_improvements(self, original_task: str, optimized_task: str) -> List[str]:
        """分析优化改进点
        
        Args:
            original_task: 原始任务描述
            optimized_task: 优化后任务描述
            
        Returns:
            改进点列表
        """
        improvements = []
        
        # 检查步骤编号
        if "1." in optimized_task and "1." not in original_task:
            improvements.append("添加了清晰的步骤编号")
        
        # 检查具体文件名
        if (".png" in optimized_task or ".csv" in optimized_task or ".json" in optimized_task) and \
           (".png" not in original_task and ".csv" not in original_task and ".json" not in original_task):
            improvements.append("明确了输出文件格式和名称")
        
        # 检查验证条件
        if ("如果" in optimized_task or "完成标志" in optimized_task) and \
           ("如果" not in original_task and "完成标志" not in original_task):
            improvements.append("添加了验证和错误处理条件")
        
        # 检查约束条件
        if ("限制" in optimized_task or "只在" in optimized_task or "必须" in optimized_task) and \
           len(optimized_task) > len(original_task) * 1.2:
            improvements.append("增加了明确的约束和限制条件")
        
        # 检查任务结构化
        if len(optimized_task.split('\n')) > len(original_task.split('\n')):
            improvements.append("优化了任务结构和可读性")
        
        # 检查Browser-Use特性
        if ("等待" in optimized_task or "截图" in optimized_task or "保存" in optimized_task) and \
           ("等待" not in original_task or "截图" not in original_task or "保存" not in original_task):
            improvements.append("添加了Browser-Use特定的操作要求")
        
        # 如果没有发现明显改进，添加通用改进
        if not improvements:
            improvements.append("优化了任务描述的清晰度和可执行性")
        
        return improvements
    
    def _validate_optimized_task(self, optimized_task: str) -> bool:
        """验证优化后的任务描述
        
        Args:
            optimized_task: 优化后的任务描述
            
        Returns:
            是否通过验证
        """
        if not optimized_task or len(optimized_task.strip()) < 10:
            logger.warning("优化后的任务描述过短", length=len(optimized_task.strip()))
            return False
        
        # 检查是否包含不应该有的标记
        invalid_markers = ["```", "**", "##", "###"]
        for marker in invalid_markers:
            if marker in optimized_task:
                logger.warning("优化后的任务描述包含格式标记", marker=marker)
                return False
        
        # 检查长度合理性
        if len(optimized_task) > 2000:
            logger.warning("优化后的任务描述过长", length=len(optimized_task))
            return False
        
        return True
    
    async def optimize_task_description(self, 
                                      task_description: str, 
                                      language: str = "zh",
                                      max_retries: int = 3) -> OptimizationResult:
        """优化任务描述
        
        Args:
            task_description: 原始任务描述
            language: 目标语言，默认中文
            max_retries: 最大重试次数
            
        Returns:
            优化结果对象
        """
        start_time = time.time()
        
        if not self.llm:
            error_msg = "Azure OpenAI LLM未初始化"
            logger.error(error_msg)
            return OptimizationResult(
                success=False,
                original_task=task_description,
                optimized_task=task_description,
                optimization_time=0.0,
                improvements=[],
                error_message=error_msg
            )
        
        if not task_description or len(task_description.strip()) < 5:
            error_msg = "任务描述过短或为空"
            logger.warning(error_msg, task_length=len(task_description.strip()))
            return OptimizationResult(
                success=False,
                original_task=task_description,
                optimized_task=task_description,
                optimization_time=0.0,
                improvements=[],
                error_message=error_msg
            )
        
        for attempt in range(max_retries):
            try:
                logger.info("开始优化任务描述", 
                           attempt=attempt + 1, 
                           task_length=len(task_description),
                           language=language)
                
                # 构建消息
                messages = [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": self._format_optimization_prompt(task_description, language)}
                ]
                
                # 调用LLM
                response = await self.llm.ainvoke(messages)
                optimized_task = response.content.strip()
                
                # 验证结果
                if not self._validate_optimized_task(optimized_task):
                    if attempt < max_retries - 1:
                        logger.warning("优化结果验证失败，重试", attempt=attempt + 1)
                        continue
                    else:
                        error_msg = "优化结果验证失败，已达到最大重试次数"
                        logger.error(error_msg)
                        return OptimizationResult(
                            success=False,
                            original_task=task_description,
                            optimized_task=task_description,
                            optimization_time=time.time() - start_time,
                            improvements=[],
                            error_message=error_msg
                        )
                
                # 分析改进点
                improvements = self._analyze_improvements(task_description, optimized_task)
                optimization_time = time.time() - start_time
                
                logger.info("任务描述优化成功", 
                           optimization_time=optimization_time,
                           original_length=len(task_description),
                           optimized_length=len(optimized_task),
                           improvements_count=len(improvements))
                
                return OptimizationResult(
                    success=True,
                    original_task=task_description,
                    optimized_task=optimized_task,
                    optimization_time=optimization_time,
                    improvements=improvements
                )
                
            except Exception as e:
                logger.warning("任务优化尝试失败", 
                              attempt=attempt + 1, 
                              error=str(e))
                
                if attempt < max_retries - 1:
                    continue
                else:
                    error_msg = f"任务优化失败，已达到最大重试次数: {str(e)}"
                    logger.error(error_msg)
                    return OptimizationResult(
                        success=False,
                        original_task=task_description,
                        optimized_task=task_description,
                        optimization_time=time.time() - start_time,
                        improvements=[],
                        error_message=error_msg
                    )
    
    def optimize_task_description_sync(self, 
                                     task_description: str, 
                                     language: str = "zh",
                                     max_retries: int = 3) -> OptimizationResult:
        """同步版本的任务优化（用于非异步环境）
        
        Args:
            task_description: 原始任务描述
            language: 目标语言，默认中文
            max_retries: 最大重试次数
            
        Returns:
            优化结果对象
        """
        import asyncio
        
        try:
            # 获取或创建事件循环
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果循环正在运行，使用run_in_executor
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run, 
                        self.optimize_task_description(task_description, language, max_retries)
                    )
                    return future.result()
            else:
                # 如果循环未运行，直接运行
                return loop.run_until_complete(
                    self.optimize_task_description(task_description, language, max_retries)
                )
        except Exception as e:
            logger.error("同步任务优化失败", error=str(e))
            return OptimizationResult(
                success=False,
                original_task=task_description,
                optimized_task=task_description,
                optimization_time=0.0,
                improvements=[],
                error_message=f"同步优化失败: {str(e)}"
            )


# 全局优化器实例
task_optimizer = TaskOptimizer() 