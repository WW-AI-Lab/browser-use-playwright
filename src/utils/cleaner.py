"""工作流脚本清理和优化工具"""
import re
from typing import Dict, List, Optional, Set, Tuple

from ..models.workflow import Workflow, WorkflowStep, StepType
from ..utils.logger import logger


class ScriptCleaner:
    """脚本清理器 - 优化录制的工作流"""
    
    def __init__(self):
        """初始化清理器"""
        self.optimization_stats = {
            "removed_duplicates": 0,
            "optimized_waits": 0,
            "improved_selectors": 0,
            "merged_steps": 0
        }
        
        logger.info("ScriptCleaner初始化完成")
    
    def clean_workflow(self, workflow: Workflow) -> Workflow:
        """清理整个工作流
        
        Args:
            workflow: 原始工作流
            
        Returns:
            清理后的工作流
        """
        logger.info("开始清理工作流", workflow_name=workflow.name)
        
        # 重置统计信息
        self.optimization_stats = {
            "removed_duplicates": 0,
            "optimized_waits": 0,
            "improved_selectors": 0,
            "merged_steps": 0
        }
        
        # 创建工作流副本
        cleaned_workflow = Workflow(**workflow.model_dump())
        
        # 执行各种清理操作
        cleaned_workflow = self._remove_duplicate_steps(cleaned_workflow)
        cleaned_workflow = self._optimize_wait_steps(cleaned_workflow)
        cleaned_workflow = self._improve_selectors(cleaned_workflow)
        cleaned_workflow = self._merge_similar_steps(cleaned_workflow)
        cleaned_workflow = self._remove_redundant_navigation(cleaned_workflow)
        cleaned_workflow = self._optimize_step_order(cleaned_workflow)
        
        logger.info("工作流清理完成", 
                   workflow_name=workflow.name,
                   original_steps=len(workflow.steps),
                   cleaned_steps=len(cleaned_workflow.steps),
                   stats=self.optimization_stats)
        
        return cleaned_workflow
    
    def _remove_duplicate_steps(self, workflow: Workflow) -> Workflow:
        """去除重复步骤"""
        seen_steps: Set[str] = set()
        unique_steps: List[WorkflowStep] = []
        
        for step in workflow.steps:
            # 创建步骤的唯一标识
            step_signature = self._get_step_signature(step)
            
            if step_signature not in seen_steps:
                seen_steps.add(step_signature)
                unique_steps.append(step)
            else:
                self.optimization_stats["removed_duplicates"] += 1
                logger.debug("移除重复步骤", step_id=step.id, signature=step_signature)
        
        workflow.steps = unique_steps
        return workflow
    
    def _optimize_wait_steps(self, workflow: Workflow) -> Workflow:
        """优化等待步骤，替换sleep为智能等待"""
        optimized_steps: List[WorkflowStep] = []
        
        for i, step in enumerate(workflow.steps):
            if step.type == StepType.WAIT:
                # 检查是否是简单的时间等待
                if step.timeout and not step.selector and not step.wait_condition:
                    # 尝试找到更好的等待条件
                    next_step = workflow.steps[i + 1] if i + 1 < len(workflow.steps) else None
                    
                    if next_step and next_step.selector:
                        # 将时间等待转换为元素等待
                        step.selector = next_step.selector
                        step.wait_condition = "visible"
                        step.description = f"等待 {next_step.selector} 可见"
                        
                        self.optimization_stats["optimized_waits"] += 1
                        logger.debug("优化等待步骤", step_id=step.id, new_selector=step.selector)
            
            optimized_steps.append(step)
        
        workflow.steps = optimized_steps
        return workflow
    
    def _improve_selectors(self, workflow: Workflow) -> Workflow:
        """改进选择器，使其更稳定和可读"""
        for step in workflow.steps:
            if step.selector:
                original_selector = step.selector
                improved_selector = self._optimize_selector(step.selector)
                
                if improved_selector != original_selector:
                    step.selector = improved_selector
                    self.optimization_stats["improved_selectors"] += 1
                    logger.debug("改进选择器", 
                               step_id=step.id,
                               original=original_selector,
                               improved=improved_selector)
        
        return workflow
    
    def _optimize_selector(self, selector: str) -> str:
        """优化单个选择器"""
        # 移除过于具体的索引选择器
        selector = re.sub(r':nth-child\(\d+\)', '', selector)
        
        # 优先使用有意义的属性
        if 'id=' in selector:
            # ID选择器通常最稳定
            id_match = re.search(r'id=["\']([^"\']+)["\']', selector)
            if id_match:
                return f"#{id_match.group(1)}"
        
        if 'data-testid=' in selector:
            # 测试ID是很好的选择器
            testid_match = re.search(r'data-testid=["\']([^"\']+)["\']', selector)
            if testid_match:
                return f"[data-testid='{testid_match.group(1)}']"
        
        if 'name=' in selector:
            # name属性也比较稳定
            name_match = re.search(r'name=["\']([^"\']+)["\']', selector)
            if name_match:
                return f"[name='{name_match.group(1)}']"
        
        # 简化复杂的选择器
        selector = re.sub(r'\s*>\s*', ' > ', selector)
        selector = re.sub(r'\s+', ' ', selector).strip()
        
        return selector
    
    def _merge_similar_steps(self, workflow: Workflow) -> Workflow:
        """合并相似的连续步骤"""
        merged_steps: List[WorkflowStep] = []
        i = 0
        
        while i < len(workflow.steps):
            current_step = workflow.steps[i]
            
            # 检查是否可以与下一步合并
            if i + 1 < len(workflow.steps):
                next_step = workflow.steps[i + 1]
                merged_step = self._try_merge_steps(current_step, next_step)
                
                if merged_step:
                    merged_steps.append(merged_step)
                    self.optimization_stats["merged_steps"] += 1
                    logger.debug("合并步骤", 
                               step1_id=current_step.id,
                               step2_id=next_step.id,
                               merged_id=merged_step.id)
                    i += 2  # 跳过下一步
                    continue
            
            merged_steps.append(current_step)
            i += 1
        
        workflow.steps = merged_steps
        return workflow
    
    def _try_merge_steps(self, step1: WorkflowStep, step2: WorkflowStep) -> Optional[WorkflowStep]:
        """尝试合并两个步骤"""
        # 合并连续的填写操作到同一个表单
        if (step1.type == StepType.FILL and step2.type == StepType.FILL and
            step1.selector and step2.selector and
            self._are_same_form(step1.selector, step2.selector)):
            
            # 创建合并后的步骤
            merged_step = WorkflowStep(
                id=f"merged_{step1.id}_{step2.id}",
                type=StepType.CUSTOM,
                description=f"填写表单: {step1.description}, {step2.description}",
                metadata={
                    "merged_steps": [step1.model_dump(), step2.model_dump()],
                    "type": "form_fill"
                }
            )
            return merged_step
        
        return None
    
    def _are_same_form(self, selector1: str, selector2: str) -> bool:
        """判断两个选择器是否属于同一个表单"""
        # 简单的启发式判断
        # 如果选择器都包含form相关的父元素，认为是同一个表单
        form_indicators = ['form', '.form', '#form', '[role="form"]']
        
        for indicator in form_indicators:
            if indicator in selector1 and indicator in selector2:
                return True
        
        return False
    
    def _remove_redundant_navigation(self, workflow: Workflow) -> Workflow:
        """移除冗余的导航步骤"""
        filtered_steps: List[WorkflowStep] = []
        last_url: Optional[str] = None
        
        for step in workflow.steps:
            if step.type == StepType.NAVIGATE:
                if step.url != last_url:
                    filtered_steps.append(step)
                    last_url = step.url
                else:
                    logger.debug("移除冗余导航", step_id=step.id, url=step.url)
            else:
                filtered_steps.append(step)
        
        workflow.steps = filtered_steps
        return workflow
    
    def _optimize_step_order(self, workflow: Workflow) -> Workflow:
        """优化步骤顺序"""
        # 将等待步骤移动到相关操作之前
        optimized_steps: List[WorkflowStep] = []
        wait_steps: List[WorkflowStep] = []
        
        for step in workflow.steps:
            if step.type == StepType.WAIT:
                wait_steps.append(step)
            else:
                # 在操作步骤前添加相关的等待步骤
                for wait_step in wait_steps:
                    if (wait_step.selector and step.selector and 
                        wait_step.selector == step.selector):
                        optimized_steps.append(wait_step)
                        wait_steps.remove(wait_step)
                        break
                
                optimized_steps.append(step)
        
        # 添加剩余的等待步骤
        optimized_steps.extend(wait_steps)
        
        workflow.steps = optimized_steps
        return workflow
    
    def _get_step_signature(self, step: WorkflowStep) -> str:
        """获取步骤的唯一签名"""
        key_parts = [
            step.type.value,
            step.selector or "",
            step.url or "",
            step.value or ""
        ]
        return "|".join(key_parts)
    
    def add_parameterization(self, workflow: Workflow, 
                           selectors_to_parameterize: List[str]) -> Workflow:
        """添加参数化 - 将硬编码值转换为变量"""
        from ..models.workflow import WorkflowVariable
        
        for i, step in enumerate(workflow.steps):
            if step.type == StepType.FILL and step.value:
                # 检查是否需要参数化
                if any(selector in (step.selector or "") for selector in selectors_to_parameterize):
                    # 创建变量
                    var_name = f"input_{i + 1}"
                    variable = WorkflowVariable(
                        name=var_name,
                        type="string",
                        description=f"输入值: {step.description}",
                        default=step.value,
                        required=True
                    )
                    
                    # 添加变量到工作流
                    workflow.add_variable(variable)
                    
                    # 更新步骤值为变量引用
                    step.value = f"{{{{ {var_name} }}}}"
                    
                    logger.info("添加参数化", 
                               step_id=step.id,
                               variable=var_name,
                               original_value=variable.default)
        
        return workflow
    
    def get_optimization_report(self) -> Dict[str, any]:
        """获取优化报告"""
        return {
            "optimization_stats": self.optimization_stats,
            "total_optimizations": sum(self.optimization_stats.values()),
            "recommendations": self._generate_recommendations()
        }
    
    def _generate_recommendations(self) -> List[str]:
        """生成优化建议"""
        recommendations = []
        
        if self.optimization_stats["removed_duplicates"] > 0:
            recommendations.append("检测到重复步骤，已自动移除")
        
        if self.optimization_stats["optimized_waits"] > 0:
            recommendations.append("已将时间等待优化为智能等待")
        
        if self.optimization_stats["improved_selectors"] > 0:
            recommendations.append("已优化选择器以提高稳定性")
        
        if sum(self.optimization_stats.values()) == 0:
            recommendations.append("工作流已经很优化了！")
        
        return recommendations
