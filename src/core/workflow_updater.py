"""
工作流更新管理器
负责备份原始工作流、替换失败步骤、验证更新后的工作流
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from ..models.error import ValidationResult, HealingSession
from ..utils.logger import get_logger

logger = get_logger(__name__)


class WorkflowUpdater:
    """工作流更新管理器"""
    
    def __init__(self, backup_dir: str = "workflows/backups"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"工作流更新器初始化完成，备份目录: {self.backup_dir}")
    
    async def backup_original(self, workflow_path: str) -> str:
        """备份原始工作流"""
        try:
            workflow_path = Path(workflow_path)
            if not workflow_path.exists():
                raise FileNotFoundError(f"工作流文件不存在: {workflow_path}")
            
            # 生成备份文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{workflow_path.stem}_backup_{timestamp}{workflow_path.suffix}"
            backup_path = self.backup_dir / backup_name
            
            # 复制文件
            shutil.copy2(workflow_path, backup_path)
            
            logger.info(f"工作流备份完成: {workflow_path} -> {backup_path}")
            return str(backup_path)
            
        except Exception as e:
            logger.error(f"备份工作流失败: {e}")
            raise
    
    async def replace_failed_steps(
        self,
        workflow: Dict[str, Any],
        failed_index: int,
        new_steps: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """替换失败步骤"""
        try:
            logger.info(f"替换失败步骤: 索引 {failed_index}, 新步骤数量: {len(new_steps)}")
            
            # 创建工作流副本
            updated_workflow = workflow.copy()
            steps = updated_workflow.get("steps", [])
            
            if failed_index >= len(steps):
                raise ValueError(f"步骤索引超出范围: {failed_index}")
            
            # 记录原始失败步骤
            original_step = steps[failed_index]
            logger.info(f"原始失败步骤: {original_step}")
            
            # 替换步骤
            if new_steps:
                # 用新步骤替换失败步骤
                steps[failed_index:failed_index+1] = new_steps
                
                # 添加元数据
                for i, step in enumerate(new_steps):
                    step["replaced_original"] = original_step
                    step["replacement_index"] = i
                    step["replacement_timestamp"] = datetime.now().isoformat()
            else:
                # 如果没有新步骤，标记原步骤为跳过
                steps[failed_index]["status"] = "skipped"
                steps[failed_index]["skip_reason"] = "healing_failed"
                steps[failed_index]["skip_timestamp"] = datetime.now().isoformat()
            
            # 更新工作流元数据
            updated_workflow["steps"] = steps
            updated_workflow["last_updated"] = datetime.now().isoformat()
            updated_workflow["healing_applied"] = True
            
            # 记录修改历史
            if "healing_history" not in updated_workflow:
                updated_workflow["healing_history"] = []
            
            updated_workflow["healing_history"].append({
                "timestamp": datetime.now().isoformat(),
                "failed_step_index": failed_index,
                "original_step": original_step,
                "new_steps_count": len(new_steps),
                "action": "replace_failed_steps"
            })
            
            logger.info(f"步骤替换完成，工作流现有 {len(steps)} 个步骤")
            return updated_workflow
            
        except Exception as e:
            logger.error(f"替换失败步骤时出错: {e}")
            raise
    
    async def validate_updated_workflow(self, workflow: Dict[str, Any]) -> ValidationResult:
        """验证更新后的工作流"""
        try:
            logger.info("开始验证更新后的工作流")
            
            errors = []
            warnings = []
            score = 1.0
            
            # 检查基本结构
            if "steps" not in workflow:
                errors.append("工作流缺少 'steps' 字段")
                score -= 0.5
            
            if "name" not in workflow:
                warnings.append("工作流缺少 'name' 字段")
                score -= 0.1
            
            # 检查步骤
            steps = workflow.get("steps", [])
            if not steps:
                errors.append("工作流没有步骤")
                score -= 0.3
            
            # 验证每个步骤
            for i, step in enumerate(steps):
                step_errors = await self._validate_step(step, i)
                errors.extend(step_errors)
                if step_errors:
                    score -= 0.1 * len(step_errors)
            
            # 检查自愈步骤的连贯性
            healing_warnings = await self._validate_healing_coherence(workflow)
            warnings.extend(healing_warnings)
            if healing_warnings:
                score -= 0.05 * len(healing_warnings)
            
            # 确保分数不为负
            score = max(0.0, score)
            
            is_valid = len(errors) == 0 and score >= 0.7
            
            result = ValidationResult(
                is_valid=is_valid,
                errors=errors,
                warnings=warnings,
                score=score
            )
            
            logger.info(f"工作流验证完成: 有效={is_valid}, 分数={score:.2f}, 错误={len(errors)}, 警告={len(warnings)}")
            return result
            
        except Exception as e:
            logger.error(f"验证工作流失败: {e}")
            return ValidationResult(
                is_valid=False,
                errors=[f"验证过程出错: {str(e)}"],
                score=0.0
            )
    
    async def _validate_step(self, step: Dict[str, Any], index: int) -> List[str]:
        """验证单个步骤"""
        errors = []
        
        # 检查必需字段
        if "type" not in step:
            errors.append(f"步骤 {index} 缺少 'type' 字段")
        
        step_type = step.get("type")
        
        # 根据步骤类型验证特定字段
        if step_type == "click":
            if "selector" not in step and "coordinates" not in step:
                errors.append(f"步骤 {index} (click) 缺少 'selector' 或 'coordinates' 字段")
        
        elif step_type == "type":
            if "selector" not in step:
                errors.append(f"步骤 {index} (type) 缺少 'selector' 字段")
            if "value" not in step:
                errors.append(f"步骤 {index} (type) 缺少 'value' 字段")
        
        elif step_type == "navigate":
            if "url" not in step:
                errors.append(f"步骤 {index} (navigate) 缺少 'url' 字段")
        
        elif step_type == "wait":
            if "selector" not in step and "timeout" not in step:
                errors.append(f"步骤 {index} (wait) 缺少 'selector' 或 'timeout' 字段")
        
        return errors
    
    async def _validate_healing_coherence(self, workflow: Dict[str, Any]) -> List[str]:
        """验证自愈步骤的连贯性"""
        warnings = []
        steps = workflow.get("steps", [])
        
        # 检查自愈步骤的连续性
        healing_steps = []
        for i, step in enumerate(steps):
            if step.get("generated_by") == "browser_use_healer":
                healing_steps.append((i, step))
        
        # 检查自愈步骤是否过于分散
        if len(healing_steps) > 1:
            indices = [i for i, _ in healing_steps]
            max_gap = max(indices[i+1] - indices[i] for i in range(len(indices)-1))
            if max_gap > 5:
                warnings.append("自愈步骤分布过于分散，可能影响执行连贯性")
        
        # 检查自愈步骤的原始步骤索引一致性
        original_indices = set()
        for _, step in healing_steps:
            original_index = step.get("original_step_index")
            if original_index is not None:
                original_indices.add(original_index)
        
        if len(original_indices) > 1:
            warnings.append("多个不同的原始步骤被替换，可能需要人工审查")
        
        return warnings
    
    async def save_updated_workflow(self, workflow: Dict[str, Any], path: str) -> bool:
        """保存更新后的工作流"""
        try:
            workflow_path = Path(path)
            
            # 确保目录存在
            workflow_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 保存工作流
            with open(workflow_path, 'w', encoding='utf-8') as f:
                json.dump(workflow, f, indent=2, ensure_ascii=False)
            
            logger.info(f"更新后的工作流已保存: {workflow_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存工作流失败: {e}")
            return False
    
    async def apply_healing_session(self, workflow_path: str, healing_session: HealingSession) -> str:
        """应用自愈会话到工作流"""
        try:
            logger.info(f"应用自愈会话到工作流: {workflow_path}")
            
            # 加载原始工作流
            with open(workflow_path, 'r', encoding='utf-8') as f:
                workflow = json.load(f)
            
            # 备份原始工作流
            backup_path = await self.backup_original(workflow_path)
            
            # 替换失败步骤
            updated_workflow = await self.replace_failed_steps(
                workflow,
                healing_session.error_context.step_index,
                healing_session.new_steps
            )
            
            # 添加自愈会话信息
            updated_workflow["applied_healing_session"] = {
                "session_id": healing_session.session_id,
                "timestamp": datetime.now().isoformat(),
                "success": healing_session.success,
                "backup_path": backup_path
            }
            
            # 验证更新后的工作流
            validation_result = await self.validate_updated_workflow(updated_workflow)
            
            if not validation_result.is_valid:
                logger.warning(f"更新后的工作流验证失败: {validation_result.errors}")
                # 可以选择是否继续保存
            
            # 保存更新后的工作流
            success = await self.save_updated_workflow(updated_workflow, workflow_path)
            
            if success:
                logger.info(f"自愈会话应用成功: {healing_session.session_id}")
                return workflow_path
            else:
                raise Exception("保存更新后的工作流失败")
                
        except Exception as e:
            logger.error(f"应用自愈会话失败: {e}")
            raise
    
    async def rollback_workflow(self, workflow_path: str, backup_path: str) -> bool:
        """回滚工作流到备份版本"""
        try:
            workflow_path = Path(workflow_path)
            backup_path = Path(backup_path)
            
            if not backup_path.exists():
                raise FileNotFoundError(f"备份文件不存在: {backup_path}")
            
            # 复制备份文件到原位置
            shutil.copy2(backup_path, workflow_path)
            
            logger.info(f"工作流回滚成功: {backup_path} -> {workflow_path}")
            return True
            
        except Exception as e:
            logger.error(f"工作流回滚失败: {e}")
            return False
    
    async def get_workflow_history(self, workflow_path: str) -> List[Dict[str, Any]]:
        """获取工作流修改历史"""
        try:
            with open(workflow_path, 'r', encoding='utf-8') as f:
                workflow = json.load(f)
            
            return workflow.get("healing_history", [])
            
        except Exception as e:
            logger.error(f"获取工作流历史失败: {e}")
            return []
    
    async def cleanup_old_backups(self, days: int = 30) -> int:
        """清理旧的备份文件"""
        try:
            cutoff_time = datetime.now().timestamp() - (days * 24 * 3600)
            cleaned_count = 0
            
            for backup_file in self.backup_dir.glob("*_backup_*"):
                if backup_file.stat().st_mtime < cutoff_time:
                    backup_file.unlink()
                    cleaned_count += 1
            
            logger.info(f"清理了 {cleaned_count} 个旧备份文件")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"清理备份文件失败: {e}")
            return 0 