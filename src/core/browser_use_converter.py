"""Browser-Use操作转换器

将Browser-Use录制的custom步骤转换为Playwright可执行的标准步骤
"""

import ast
import re
import json
from typing import Dict, Any, List, Optional, Tuple
from structlog import get_logger

from src.models.workflow import WorkflowStep, StepType

logger = get_logger(__name__)


class BrowserUseConverter:
    """Browser-Use操作转换器
    
    将Browser-Use录制的操作转换为Playwright执行器可理解的标准操作
    """
    
    def __init__(self):
        """初始化转换器"""
        self.operation_map = {
            'open_tab': self._convert_open_tab,
            'input_text': self._convert_input_text,
            'click_element_by_index': self._convert_click_element,
            'scroll_down': self._convert_scroll,
            'scroll_up': self._convert_scroll,
            'switch_tab': self._convert_switch_tab,
            'extract_content': self._convert_extract_content,
            'save_pdf': self._convert_save_pdf,
            'done': self._convert_done,
            'wait': self._convert_wait,
            'hover': self._convert_hover,
            'press_key': self._convert_press_key
        }
        
        logger.info("Browser-Use转换器初始化完成", supported_operations=list(self.operation_map.keys()))
    
    def can_convert_step(self, step: WorkflowStep) -> bool:
        """检查步骤是否可以转换"""
        if step.type != StepType.CUSTOM:
            return False
        
        if not step.value:
            return False
        
        # 检查是否包含Browser-Use操作
        browser_use_ops = self._extract_browser_use_operations(step.value)
        return len(browser_use_ops) > 0
    
    def convert_step(self, step: WorkflowStep) -> List[WorkflowStep]:
        """转换单个步骤
        
        Args:
            step: 要转换的Browser-Use custom步骤
            
        Returns:
            转换后的标准步骤列表
        """
        if not self.can_convert_step(step):
            logger.warning("步骤无法转换", step_id=step.id, step_type=step.type.value)
            return [step]  # 返回原步骤
        
        try:
            # 解析Browser-Use操作
            operations = self._parse_browser_use_value(step.value)
            if not operations:
                logger.warning("无法解析Browser-Use操作", step_id=step.id)
                return [step]
            
            # 转换操作
            converted_steps = []
            for i, (op_name, op_data) in enumerate(operations.items()):
                if op_name == 'interacted_element':
                    continue  # 跳过交互元素信息，这只是元数据
                
                converter_func = self.operation_map.get(op_name)
                if converter_func:
                    try:
                        new_steps = converter_func(op_data, step, i)
                        if new_steps:
                            converted_steps.extend(new_steps)
                    except Exception as e:
                        logger.error("转换操作失败", operation=op_name, error=str(e), step_id=step.id)
                        # 创建一个备用步骤
                        fallback_step = self._create_fallback_step(step, op_name, op_data, i)
                        converted_steps.append(fallback_step)
                else:
                    logger.warning("不支持的操作类型", operation=op_name, step_id=step.id)
                    # 创建一个备用步骤
                    fallback_step = self._create_fallback_step(step, op_name, op_data, i)
                    converted_steps.append(fallback_step)
            
            if not converted_steps:
                logger.warning("转换结果为空", step_id=step.id)
                return [step]
            
            logger.info("步骤转换成功", 
                       original_step_id=step.id,
                       converted_count=len(converted_steps),
                       operations=list(operations.keys()))
            
            return converted_steps
            
        except Exception as e:
            logger.error("步骤转换失败", step_id=step.id, error=str(e), exc_info=True)
            return [step]  # 返回原步骤
    
    def convert_workflow_steps(self, steps: List[WorkflowStep]) -> List[WorkflowStep]:
        """转换整个工作流的步骤列表
        
        Args:
            steps: 原始步骤列表
            
        Returns:
            转换后的步骤列表
        """
        converted_steps = []
        
        for step in steps:
            if self.can_convert_step(step):
                new_steps = self.convert_step(step)
                converted_steps.extend(new_steps)
            else:
                converted_steps.append(step)
        
        logger.info("工作流步骤转换完成",
                   original_count=len(steps),
                   converted_count=len(converted_steps))
        
        return converted_steps
    
    def convert_workflow(self, workflow):
        """转换整个工作流
        
        Args:
            workflow: 要转换的工作流对象
            
        Returns:
            转换后的工作流对象
        """
        # 导入放在这里避免循环导入
        from src.models.workflow import Workflow
        
        # 转换步骤
        converted_steps = self.convert_workflow_steps(workflow.steps)
        
        # 创建新的工作流对象
        converted_workflow = Workflow(
            name=workflow.name,
            description=workflow.description,
            version=workflow.version,
            steps=converted_steps,
            variables=workflow.variables,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at
        )
        
        # 复制其他属性
        if hasattr(workflow, 'tags'):
            converted_workflow.tags = workflow.tags
        if hasattr(workflow, 'author'):
            converted_workflow.author = workflow.author
        
        logger.info("工作流转换完成",
                   workflow_name=workflow.name,
                   original_steps=len(workflow.steps),
                   converted_steps=len(converted_steps))
        
        return converted_workflow
    
    def _extract_browser_use_operations(self, step_value: str) -> List[str]:
        """提取Browser-Use操作类型"""
        operations = []
        
        for op in ['open_tab', 'click_element_by_index', 'input_text', 'scroll_down', 
                  'scroll_up', 'switch_tab', 'extract_content', 'save_pdf', 'done',
                  'wait', 'hover', 'press_key']:
            if op in step_value:
                operations.append(op)
        
        return operations
    
    def _parse_browser_use_value(self, step_value: str) -> Dict[str, Any]:
        """解析Browser-Use步骤值"""
        try:
            # 处理包含DOMHistoryElement等复杂对象的情况
            if 'DOMHistoryElement(' in step_value:
                # 先提取不含复杂对象的基本操作
                operations = {}
                
                # 提取open_tab操作
                open_tab_match = re.search(r"'open_tab':\s*({[^}]+})", step_value)
                if open_tab_match:
                    try:
                        operations['open_tab'] = ast.literal_eval(open_tab_match.group(1))
                    except:
                        operations['open_tab'] = {'url': 'https://www.douban.com'}
                
                # 提取input_text操作
                input_text_match = re.search(r"'input_text':\s*({[^}]+})", step_value)
                if input_text_match:
                    try:
                        operations['input_text'] = ast.literal_eval(input_text_match.group(1))
                    except:
                        pass
                
                # 提取click_element_by_index操作
                click_match = re.search(r"'click_element_by_index':\s*({[^}]+})", step_value)
                if click_match:
                    try:
                        operations['click_element_by_index'] = ast.literal_eval(click_match.group(1))
                    except:
                        pass
                
                # 提取其他简单操作
                for op in ['scroll_down', 'scroll_up', 'switch_tab', 'save_pdf']:
                    if f"'{op}'" in step_value:
                        # 尝试提取参数
                        op_match = re.search(rf"'{op}':\s*({{[^}}]*}})", step_value)
                        if op_match:
                            try:
                                operations[op] = ast.literal_eval(op_match.group(1))
                            except:
                                operations[op] = {}
                        else:
                            operations[op] = {}
                
                # 提取extract_content操作
                extract_match = re.search(r"'extract_content':\s*({[^}]+?'goal':[^}]+})", step_value)
                if extract_match:
                    try:
                        operations['extract_content'] = ast.literal_eval(extract_match.group(1))
                    except:
                        operations['extract_content'] = {'goal': 'Extract content'}
                
                # 提取done操作
                done_match = re.search(r"'done':\s*({.+?'success':\s*True[^}]*})", step_value)
                if done_match:
                    try:
                        operations['done'] = ast.literal_eval(done_match.group(1))
                    except:
                        operations['done'] = {'success': True}
                
                return operations
            
            # 尝试直接解析
            try:
                return ast.literal_eval(step_value)
            except:
                # 如果解析失败，尝试JSON解析
                try:
                    # 将单引号替换为双引号
                    json_str = step_value.replace("'", '"')
                    return json.loads(json_str)
                except:
                    logger.warning("无法解析步骤值", value=step_value[:100])
                    return {}
                    
        except Exception as e:
            logger.error("解析Browser-Use值失败", error=str(e), value=step_value[:100])
            return {}
    
    def _create_fallback_step(self, original_step: WorkflowStep, op_name: str, op_data: Any, index: int) -> WorkflowStep:
        """创建备用步骤"""
        return WorkflowStep(
            id=f"{original_step.id}_fallback_{index}",
            type=StepType.CUSTOM,
            description=f"未转换的Browser-Use操作: {op_name}",
            value=str(op_data),
            metadata={
                'original_step_id': original_step.id,
                'browser_use_operation': op_name,
                'conversion_failed': True
            }
        )
    
    # 转换器方法
    def _convert_open_tab(self, op_data: Dict[str, Any], original_step: WorkflowStep, index: int) -> List[WorkflowStep]:
        """转换open_tab操作为navigate步骤"""
        url = op_data.get('url', 'https://www.douban.com')
        
        return [WorkflowStep(
            id=f"{original_step.id}_navigate_{index}",
            type=StepType.NAVIGATE,
            description=f"导航到 {url}",
            url=url,
            timeout=30000,
            metadata={
                'original_step_id': original_step.id,
                'browser_use_operation': 'open_tab',
                'converted_from': 'browser_use'
            }
        )]
    
    def _convert_input_text(self, op_data: Dict[str, Any], original_step: WorkflowStep, index: int) -> List[WorkflowStep]:
        """转换input_text操作为fill步骤"""
        text = op_data.get('text', '')
        element_index = op_data.get('index')
        
        # 如果有元素索引，尝试构建选择器
        selector = None
        if element_index is not None:
            # 基于常见的豆瓣搜索框选择器
            if element_index == 10:  # 通常是搜索框
                selector = 'input[name="q"], input[placeholder*="搜索"], #inp-query'
        
        if not selector:
            selector = 'input[type="text"], input[type="search"], textarea'
        
        return [WorkflowStep(
            id=f"{original_step.id}_fill_{index}",
            type=StepType.FILL,
            description=f"输入文本: {text}",
            selector=selector,
            value=text,
            timeout=10000,
            metadata={
                'original_step_id': original_step.id,
                'browser_use_operation': 'input_text',
                'element_index': element_index,
                'converted_from': 'browser_use'
            }
        )]
    
    def _convert_click_element(self, op_data: Dict[str, Any], original_step: WorkflowStep, index: int) -> List[WorkflowStep]:
        """转换click_element_by_index操作为click步骤"""
        element_index = op_data.get('index')
        
        # 基于常见的元素索引推测选择器
        selector = self._guess_selector_by_index(element_index)
        
        return [WorkflowStep(
            id=f"{original_step.id}_click_{index}",
            type=StepType.CLICK,
            description=f"点击元素 (索引: {element_index})",
            selector=selector,
            timeout=10000,
            wait_condition='visible',
            metadata={
                'original_step_id': original_step.id,
                'browser_use_operation': 'click_element_by_index',
                'element_index': element_index,
                'converted_from': 'browser_use'
            }
        )]
    
    def _convert_scroll(self, op_data: Dict[str, Any], original_step: WorkflowStep, index: int) -> List[WorkflowStep]:
        """转换scroll操作为scroll步骤"""
        direction = 'down' if 'scroll_down' in str(original_step.value) else 'up'
        amount = op_data.get('amount', 500)
        
        return [WorkflowStep(
            id=f"{original_step.id}_scroll_{index}",
            type=StepType.SCROLL,
            description=f"向{direction}滚动 {amount}px",
            scroll_direction=direction,
            scroll_amount=amount,
            metadata={
                'original_step_id': original_step.id,
                'browser_use_operation': f'scroll_{direction}',
                'converted_from': 'browser_use'
            }
        )]
    
    def _convert_switch_tab(self, op_data: Dict[str, Any], original_step: WorkflowStep, index: int) -> List[WorkflowStep]:
        """转换switch_tab操作为custom步骤（Playwright需要特殊处理）"""
        page_id = op_data.get('page_id', 1)
        
        return [WorkflowStep(
            id=f"{original_step.id}_switch_tab_{index}",
            type=StepType.CUSTOM,
            description=f"切换到标签页 {page_id}",
            value=json.dumps({
                'action': 'switch_tab',
                'page_id': page_id
            }),
            metadata={
                'original_step_id': original_step.id,
                'browser_use_operation': 'switch_tab',
                'page_id': page_id,
                'converted_from': 'browser_use'
            }
        )]
    
    def _convert_extract_content(self, op_data: Dict[str, Any], original_step: WorkflowStep, index: int) -> List[WorkflowStep]:
        """转换extract_content操作为extract步骤"""
        goal = op_data.get('goal', 'Extract page content')
        
        # 基于目标内容推测选择器
        selector = 'body'  # 默认提取整个页面
        if 'rating' in goal.lower():
            selector = '[class*="rating"], [class*="score"], .rating-num, .average-rating'
        elif 'summary' in goal.lower() or 'description' in goal.lower():
            selector = '[class*="intro"], [class*="summary"], [class*="description"], .content'
        
        return [WorkflowStep(
            id=f"{original_step.id}_extract_{index}",
            type=StepType.EXTRACT,
            description=f"提取内容: {goal}",
            selector=selector,
            metadata={
                'original_step_id': original_step.id,
                'browser_use_operation': 'extract_content',
                'extraction_goal': goal,
                'converted_from': 'browser_use'
            }
        )]
    
    def _convert_save_pdf(self, op_data: Dict[str, Any], original_step: WorkflowStep, index: int) -> List[WorkflowStep]:
        """转换save_pdf操作为screenshot步骤（Playwright替代方案）"""
        filename = op_data.get('filename', f'page_export_{index}.png')
        if not filename.endswith('.png'):
            filename = filename.replace('.pdf', '.png')
        
        return [WorkflowStep(
            id=f"{original_step.id}_screenshot_{index}",
            type=StepType.SCREENSHOT,
            description=f"保存页面截图: {filename}",
            screenshot_path=filename,
            metadata={
                'original_step_id': original_step.id,
                'browser_use_operation': 'save_pdf',
                'original_filename': op_data.get('filename'),
                'converted_from': 'browser_use',
                'note': 'PDF保存转换为截图保存'
            }
        )]
    
    def _convert_done(self, op_data: Dict[str, Any], original_step: WorkflowStep, index: int) -> List[WorkflowStep]:
        """转换done操作为custom步骤（记录完成状态）"""
        success = op_data.get('success', True)
        text = op_data.get('text', 'Task completed')
        
        return [WorkflowStep(
            id=f"{original_step.id}_done_{index}",
            type=StepType.CUSTOM,
            description=f"任务完成: {'成功' if success else '失败'}",
            value=json.dumps({
                'action': 'mark_completion',
                'success': success,
                'message': text
            }),
            metadata={
                'original_step_id': original_step.id,
                'browser_use_operation': 'done',
                'task_success': success,
                'completion_message': text,
                'converted_from': 'browser_use'
            }
        )]
    
    def _convert_wait(self, op_data: Dict[str, Any], original_step: WorkflowStep, index: int) -> List[WorkflowStep]:
        """转换wait操作为wait步骤"""
        timeout = op_data.get('timeout', 5000)
        selector = op_data.get('selector')
        condition = op_data.get('condition', 'visible')
        
        return [WorkflowStep(
            id=f"{original_step.id}_wait_{index}",
            type=StepType.WAIT,
            description=f"等待 {timeout}ms" + (f" - {selector}" if selector else ""),
            selector=selector,
            timeout=timeout,
            wait_condition=condition,
            metadata={
                'original_step_id': original_step.id,
                'browser_use_operation': 'wait',
                'converted_from': 'browser_use'
            }
        )]
    
    def _convert_hover(self, op_data: Dict[str, Any], original_step: WorkflowStep, index: int) -> List[WorkflowStep]:
        """转换hover操作为hover步骤"""
        selector = op_data.get('selector', 'body')
        
        return [WorkflowStep(
            id=f"{original_step.id}_hover_{index}",
            type=StepType.HOVER,
            description=f"悬停在元素上",
            selector=selector,
            timeout=10000,
            metadata={
                'original_step_id': original_step.id,
                'browser_use_operation': 'hover',
                'converted_from': 'browser_use'
            }
        )]
    
    def _convert_press_key(self, op_data: Dict[str, Any], original_step: WorkflowStep, index: int) -> List[WorkflowStep]:
        """转换press_key操作为press_key步骤"""
        key = op_data.get('key', 'Enter')
        
        return [WorkflowStep(
            id=f"{original_step.id}_press_{index}",
            type=StepType.PRESS_KEY,
            description=f"按键: {key}",
            key=key,
            metadata={
                'original_step_id': original_step.id,
                'browser_use_operation': 'press_key',
                'converted_from': 'browser_use'
            }
        )]
    
    def _guess_selector_by_index(self, element_index: Optional[int]) -> str:
        """基于元素索引推测选择器"""
        if element_index is None:
            return 'button, a, input[type="submit"], [role="button"]'
        
        # 基于常见的豆瓣网站元素索引模式
        selector_map = {
            10: 'input[name="q"], input[placeholder*="搜索"]',  # 搜索框
            12: 'input[type="submit"], button[type="submit"], .search-button',  # 搜索按钮
            36: '.subject-item a, .title a, .book-item a',  # 图书链接
            39: '.subject-item a, .title a, .book-item a'   # 图书链接替代
        }
        
        return selector_map.get(element_index, f'*:nth-child({element_index}), [data-index="{element_index}"]')


# 全局转换器实例
browser_use_converter = BrowserUseConverter() 