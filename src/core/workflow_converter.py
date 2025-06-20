"""工作流转换器

自动检测和转换Browser-Use工作流为Playwright兼容格式
"""

from pathlib import Path
from typing import Optional, Dict, Any, List
from structlog import get_logger

from src.models.workflow import Workflow, WorkflowStep, StepType
from src.core.browser_use_converter import browser_use_converter

logger = get_logger(__name__)


class WorkflowConverter:
    """工作流转换器
    
    自动检测工作流类型并转换为Playwright兼容格式
    """
    
    def __init__(self):
        """初始化工作流转换器"""
        self.conversion_stats = {
            'total_conversions': 0,
            'successful_conversions': 0,
            'failed_conversions': 0
        }
        logger.info("工作流转换器初始化完成")
    
    def is_browser_use_workflow(self, workflow: Workflow) -> bool:
        """检测是否为Browser-Use工作流"""
        # 检查是否有custom类型的步骤包含Browser-Use操作
        browser_use_steps = 0
        
        for step in workflow.steps:
            if step.type == StepType.CUSTOM and step.value:
                if browser_use_converter.can_convert_step(step):
                    browser_use_steps += 1
        
        # 如果超过30%的步骤是Browser-Use类型，则认为是Browser-Use工作流
        threshold = max(1, len(workflow.steps) * 0.3)
        is_browser_use = browser_use_steps >= threshold
        
        logger.info("工作流类型检测",
                   workflow_name=workflow.name,
                   total_steps=len(workflow.steps),
                   browser_use_steps=browser_use_steps,
                   threshold=threshold,
                   is_browser_use=is_browser_use)
        
        return is_browser_use
    
    def needs_conversion(self, workflow: Workflow) -> bool:
        """检查工作流是否需要转换
        
        Args:
            workflow: 要检查的工作流
            
        Returns:
            如果需要转换返回True，否则返回False
        """
        return self.is_browser_use_workflow(workflow)
    
    def convert_workflow(self, workflow: Workflow, auto_save: bool = True) -> Optional[Workflow]:
        """转换工作流为Playwright兼容格式
        
        Args:
            workflow: 原始工作流
            auto_save: 是否自动保存转换后的工作流
            
        Returns:
            转换后的工作流，如果转换失败则返回None
        """
        try:
            self.conversion_stats['total_conversions'] += 1
            
            # 检查是否需要转换
            if not self.is_browser_use_workflow(workflow):
                logger.info("工作流无需转换", workflow_name=workflow.name)
                return workflow
            
            logger.info("开始转换Browser-Use工作流", workflow_name=workflow.name)
            
            # 转换步骤
            converted_steps = browser_use_converter.convert_workflow_steps(workflow.steps)
            
            # 创建转换后的工作流
            converted_workflow = Workflow(
                name=f"{workflow.name}_converted",
                description=self._update_description(workflow.description),
                version=workflow.version,
                steps=converted_steps,
                variables=workflow.variables,
                created_at=workflow.created_at
            )
            
            # 分析转换效果
            conversion_analysis = self._analyze_conversion(workflow.steps, converted_steps)
            
            # 添加转换标签和作者信息
            converted_workflow.tags = ['converted', 'browser_use'] + workflow.tags
            converted_workflow.author = workflow.author or 'Browser-Use Converter'
            
            # 自动保存
            if auto_save:
                self._save_converted_workflow(converted_workflow)
            
            self.conversion_stats['successful_conversions'] += 1
            logger.info("工作流转换成功",
                       original_name=workflow.name,
                       converted_name=converted_workflow.name,
                       analysis=conversion_analysis)
            
            return converted_workflow
            
        except Exception as e:
            self.conversion_stats['failed_conversions'] += 1
            logger.error("工作流转换失败",
                        workflow_name=workflow.name,
                        error=str(e),
                        exc_info=True)
            return None
    
    def convert_workflow_file(self, file_path: str, output_dir: Optional[str] = None) -> Optional[str]:
        """转换工作流文件
        
        Args:
            file_path: 原始工作流文件路径
            output_dir: 输出目录，默认为workflows目录
            
        Returns:
            转换后的文件路径，如果转换失败则返回None
        """
        try:
            # 加载工作流
            workflow = Workflow.load_from_file(file_path)
            
            # 转换工作流
            converted_workflow = self.convert_workflow(workflow, auto_save=False)
            
            if not converted_workflow:
                return None
            
            # 确定输出路径
            if output_dir is None:
                output_dir = "workflows"
            
            output_path = Path(output_dir) / f"{converted_workflow.name}.json"
            
            # 保存转换后的工作流
            converted_workflow.save_to_file(output_path)
            
            logger.info("工作流文件转换完成",
                       input_path=file_path,
                       output_path=str(output_path))
            
            return str(output_path)
            
        except Exception as e:
            logger.error("工作流文件转换失败",
                        file_path=file_path,
                        error=str(e),
                        exc_info=True)
            return None
    
    def batch_convert_workflows(self, workflow_dir: str = "workflows") -> Dict[str, Any]:
        """批量转换工作流目录中的Browser-Use工作流
        
        Args:
            workflow_dir: 工作流目录
            
        Returns:
            转换结果统计
        """
        workflow_path = Path(workflow_dir)
        if not workflow_path.exists():
            logger.error("工作流目录不存在", directory=workflow_dir)
            return {'error': 'Directory not found'}
        
        results = {
            'total_files': 0,
            'browser_use_files': 0,
            'converted_files': 0,
            'failed_files': 0,
            'converted_workflows': []
        }
        
        # 遍历工作流文件
        for workflow_file in workflow_path.glob("*.json"):
            # 跳过已转换的文件
            if "_converted" in workflow_file.stem:
                continue
            
            results['total_files'] += 1
            
            try:
                # 加载和检测工作流
                workflow = Workflow.load_from_file(workflow_file)
                
                if self.is_browser_use_workflow(workflow):
                    results['browser_use_files'] += 1
                    
                    # 转换工作流
                    converted_workflow = self.convert_workflow(workflow)
                    
                    if converted_workflow:
                        results['converted_files'] += 1
                        results['converted_workflows'].append({
                            'original': str(workflow_file),
                            'converted': f"{workflow_dir}/{converted_workflow.name}.json",
                            'steps_count': len(converted_workflow.steps)
                        })
                    else:
                        results['failed_files'] += 1
                
            except Exception as e:
                logger.error("批量转换处理文件失败",
                           file=str(workflow_file),
                           error=str(e))
                results['failed_files'] += 1
        
        logger.info("批量转换完成", results=results)
        return results
    
    def get_conversion_stats(self) -> Dict[str, Any]:
        """获取转换统计信息"""
        return {
            **self.conversion_stats,
            'success_rate': (
                self.conversion_stats['successful_conversions'] / 
                max(1, self.conversion_stats['total_conversions'])
            ) * 100
        }
    
    def _update_description(self, original_description: str) -> str:
        """更新工作流描述，标记为已转换"""
        if not original_description:
            original_description = ""
        
        conversion_note = "\n\n[已转换] 此工作流已从Browser-Use格式转换为Playwright兼容格式"
        
        if conversion_note not in original_description:
            return original_description + conversion_note
        
        return original_description
    
    def _analyze_conversion(self, original_steps: List[WorkflowStep], 
                          converted_steps: List[WorkflowStep]) -> Dict[str, Any]:
        """分析转换效果"""
        # 统计原始步骤类型
        original_types = {}
        for step in original_steps:
            step_type = step.type.value
            original_types[step_type] = original_types.get(step_type, 0) + 1
        
        # 统计转换后步骤类型
        converted_types = {}
        for step in converted_steps:
            step_type = step.type.value
            converted_types[step_type] = converted_types.get(step_type, 0) + 1
        
        # 计算转换效果
        original_custom_steps = original_types.get('custom', 0)
        converted_custom_steps = converted_types.get('custom', 0)
        converted_standard_steps = original_custom_steps - converted_custom_steps
        
        conversion_rate = (converted_standard_steps / max(1, original_custom_steps)) * 100
        
        return {
            'original_steps_count': len(original_steps),
            'converted_steps_count': len(converted_steps),
            'original_types': original_types,
            'converted_types': converted_types,
            'converted_custom_to_standard': converted_standard_steps,
            'conversion_rate': round(conversion_rate, 1)
        }
    
    def _save_converted_workflow(self, workflow: Workflow) -> None:
        """保存转换后的工作流"""
        output_path = Path("workflows") / f"{workflow.name}.json"
        workflow.save_to_file(output_path)
        logger.info("转换后工作流已保存", path=str(output_path))


# 全局转换器实例
workflow_converter = WorkflowConverter() 