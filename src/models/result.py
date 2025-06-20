"""执行结果数据模型"""
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """执行状态枚举"""
    PENDING = "pending"          # 等待执行
    RUNNING = "running"          # 正在执行
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 执行失败
    CANCELLED = "cancelled"      # 已取消
    TIMEOUT = "timeout"          # 超时
    RETRYING = "retrying"        # 重试中


class StepResult(BaseModel):
    """步骤执行结果"""
    step_id: str = Field(..., description="步骤ID")
    step_type: str = Field(..., description="步骤类型")
    status: ExecutionStatus = Field(..., description="执行状态")
    
    # 执行信息
    start_time: datetime = Field(..., description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    duration: Optional[float] = Field(None, description="执行时长(秒)")
    
    # 结果数据
    result_data: Optional[Dict[str, Any]] = Field(None, description="执行结果数据")
    extracted_data: Optional[Dict[str, Any]] = Field(None, description="提取的数据")
    screenshot_path: Optional[str] = Field(None, description="截图路径")
    
    # 错误信息
    error_message: Optional[str] = Field(None, description="错误消息")
    error_type: Optional[str] = Field(None, description="错误类型")
    stack_trace: Optional[str] = Field(None, description="错误堆栈")
    
    # 重试信息
    retry_count: int = Field(0, description="重试次数")
    max_retries: int = Field(3, description="最大重试次数")
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")
    
    @property
    def is_completed(self) -> bool:
        """是否已完成（成功或失败）"""
        return self.status in [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, 
                              ExecutionStatus.CANCELLED, ExecutionStatus.TIMEOUT]
    
    @property
    def is_successful(self) -> bool:
        """是否执行成功"""
        return self.status == ExecutionStatus.COMPLETED
    
    def mark_success(self, result_data: Optional[Dict[str, Any]] = None, 
                    extracted_data: Optional[Dict[str, Any]] = None) -> None:
        """标记为成功"""
        self.status = ExecutionStatus.COMPLETED
        self.end_time = datetime.now()
        if self.start_time:
            self.duration = (self.end_time - self.start_time).total_seconds()
        if result_data:
            self.result_data = result_data
        if extracted_data:
            self.extracted_data = extracted_data
    
    def mark_failed(self, error_message: str, error_type: str = None, 
                   stack_trace: str = None) -> None:
        """标记为失败"""
        self.status = ExecutionStatus.FAILED
        self.end_time = datetime.now()
        if self.start_time:
            self.duration = (self.end_time - self.start_time).total_seconds()
        self.error_message = error_message
        self.error_type = error_type
        self.stack_trace = stack_trace
    
    def mark_retry(self) -> None:
        """标记为重试"""
        self.retry_count += 1
        self.status = ExecutionStatus.RETRYING


class WorkflowExecutionResult(BaseModel):
    """工作流执行结果"""
    workflow_name: str = Field(..., description="工作流名称")
    execution_id: str = Field(..., description="执行ID")
    status: ExecutionStatus = Field(ExecutionStatus.PENDING, description="总体执行状态")
    
    # 时间信息
    start_time: datetime = Field(default_factory=datetime.now, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    duration: Optional[float] = Field(None, description="总执行时长(秒)")
    
    # 步骤结果
    step_results: List[StepResult] = Field(default_factory=list, description="步骤执行结果")
    
    # 执行统计
    total_steps: int = Field(0, description="总步骤数")
    completed_steps: int = Field(0, description="已完成步骤数")
    successful_steps: int = Field(0, description="成功步骤数")
    failed_steps: int = Field(0, description="失败步骤数")
    
    # 变量和上下文
    input_variables: Dict[str, Any] = Field(default_factory=dict, description="输入变量")
    output_variables: Dict[str, Any] = Field(default_factory=dict, description="输出变量")
    context_data: Dict[str, Any] = Field(default_factory=dict, description="上下文数据")
    
    # 错误信息
    error_message: Optional[str] = Field(None, description="总体错误消息")
    failed_step_id: Optional[str] = Field(None, description="失败的步骤ID")
    
    # 资源信息
    browser_info: Optional[Dict[str, Any]] = Field(None, description="浏览器信息")
    performance_metrics: Optional[Dict[str, Any]] = Field(None, description="性能指标")
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")
    
    @property
    def is_completed(self) -> bool:
        """是否已完成"""
        return self.status in [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, 
                              ExecutionStatus.CANCELLED, ExecutionStatus.TIMEOUT]
    
    @property
    def is_successful(self) -> bool:
        """是否执行成功"""
        return self.status == ExecutionStatus.COMPLETED
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_steps == 0:
            return 0.0
        return self.successful_steps / self.total_steps
    
    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """重写model_dump方法，包含计算属性"""
        data = super().model_dump(**kwargs)
        # 添加计算属性
        data['success_rate'] = self.success_rate
        return data
    
    def add_step_result(self, step_result: StepResult) -> None:
        """添加步骤结果"""
        self.step_results.append(step_result)
        # 如果步骤完成了（无论成功失败），都计入completed_steps
        if step_result.is_completed:
            self.completed_steps += 1
        
        # 只有真正成功的步骤才计入successful_steps
        if step_result.is_successful:
            self.successful_steps += 1
        elif step_result.status == ExecutionStatus.FAILED:
            self.failed_steps += 1
    
    def get_step_result(self, step_id: str) -> Optional[StepResult]:
        """获取步骤结果"""
        for result in self.step_results:
            if result.step_id == step_id:
                return result
        return None
    
    def mark_completed(self) -> None:
        """标记为完成"""
        self.end_time = datetime.now()
        self.duration = (self.end_time - self.start_time).total_seconds()
        
        # 根据步骤结果确定总体状态
        if self.failed_steps > 0:
            self.status = ExecutionStatus.FAILED
        elif self.completed_steps == self.total_steps:
            self.status = ExecutionStatus.COMPLETED
        else:
            self.status = ExecutionStatus.FAILED
    
    def save_to_file(self, file_path: Union[str, Path]):
        """保存执行结果到文件"""
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 转换为可序列化的字典
        data = self.model_dump(mode='json')
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    
    @classmethod
    def load_from_file(cls, file_path: Union[str, Path]) -> Optional['WorkflowExecutionResult']:
        """从文件加载执行结果"""
        file_path = Path(file_path)
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return cls(**data)
        except Exception:
            return None


class BatchExecutionResult(BaseModel):
    """批量执行结果"""
    batch_id: str = Field(..., description="批次ID")
    workflow_name: str = Field(..., description="工作流名称")
    status: ExecutionStatus = Field(ExecutionStatus.PENDING, description="批次执行状态")
    
    # 时间信息
    start_time: datetime = Field(default_factory=datetime.now, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    duration: Optional[float] = Field(None, description="总执行时长(秒)")
    
    # 执行结果
    execution_results: List[WorkflowExecutionResult] = Field(
        default_factory=list, description="各次执行结果"
    )
    
    # 批次统计
    total_executions: int = Field(0, description="总执行次数")
    completed_executions: int = Field(0, description="已完成执行次数")
    successful_executions: int = Field(0, description="成功执行次数")
    failed_executions: int = Field(0, description="失败执行次数")
    
    # 配置信息
    concurrent_limit: int = Field(10, description="并发限制")
    input_data_list: List[Dict[str, Any]] = Field(
        default_factory=list, description="输入数据列表"
    )
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")
    
    @property
    def is_completed(self) -> bool:
        """是否已完成"""
        return self.status in [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, 
                              ExecutionStatus.CANCELLED, ExecutionStatus.TIMEOUT]
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_executions == 0:
            return 0.0
        return self.completed_executions / self.total_executions
    
    def add_execution_result(self, execution_result: WorkflowExecutionResult) -> None:
        """添加执行结果"""
        self.execution_results.append(execution_result)
        if execution_result.is_successful:
            self.completed_executions += 1
        else:
            self.failed_executions += 1
    
    def mark_completed(self) -> None:
        """标记为完成"""
        self.end_time = datetime.now()
        self.duration = (self.end_time - self.start_time).total_seconds()
        
        # 根据执行结果确定总体状态
        if self.failed_executions > 0:
            self.status = ExecutionStatus.FAILED if self.completed_executions == 0 else ExecutionStatus.COMPLETED
        else:
            self.status = ExecutionStatus.COMPLETED
    
    def save_to_file(self, file_path: Union[str, Path]):
        """保存批量执行结果到文件"""
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 转换为可序列化的字典
        data = self.model_dump(mode='json')
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    
    @classmethod
    def load_from_file(cls, file_path: Union[str, Path]) -> Optional['BatchExecutionResult']:
        """从文件加载批量执行结果"""
        file_path = Path(file_path)
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return cls(**data)
        except Exception:
            return None


class ExecutionHistory:
    """执行历史记录管理器"""
    
    def __init__(self, history_dir: Union[str, Path] = "./logs/executions"):
        self.history_dir = Path(history_dir)
        self.history_dir.mkdir(parents=True, exist_ok=True)
    
    def save_execution_result(self, result: WorkflowExecutionResult):
        """保存执行结果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{result.workflow_name}_{result.execution_id}_{timestamp}.json"
        file_path = self.history_dir / filename
        result.save_to_file(file_path)
    
    def save_batch_result(self, result: BatchExecutionResult):
        """保存批量执行结果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"batch_{result.workflow_name}_{result.batch_id}_{timestamp}.json"
        file_path = self.history_dir / filename
        result.save_to_file(file_path)
    
    def get_execution_history(self, workflow_name: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """获取执行历史"""
        history_files = []
        
        for file_path in self.history_dir.glob("*.json"):
            if workflow_name and workflow_name not in file_path.name:
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                history_files.append({
                    'file_path': str(file_path),
                    'filename': file_path.name,
                    'workflow_name': data.get('workflow_name'),
                    'execution_id': data.get('execution_id'),
                    'status': data.get('status'),
                    'start_time': data.get('start_time'),
                    'duration': data.get('duration'),
                    'success_rate': data.get('success_rate', 0),
                    'is_batch': 'batch_id' in data
                })
            except Exception:
                continue
        
        # 按时间排序
        history_files.sort(key=lambda x: x['start_time'] or '', reverse=True)
        
        return history_files[:limit]
    
    def get_execution_detail(self, filename: str) -> Optional[Dict[str, Any]]:
        """获取执行详情"""
        file_path = self.history_dir / filename
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    
    def cleanup_old_records(self, days: int = 30):
        """清理旧记录"""
        import time
        
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        
        for file_path in self.history_dir.glob("*.json"):
            if file_path.stat().st_mtime < cutoff_time:
                try:
                    file_path.unlink()
                except Exception:
                    pass


# 全局执行历史管理器
execution_history = ExecutionHistory()
