"""
错误数据模型定义
用于自愈功能的错误检测、分析和处理
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class ErrorType(str, Enum):
    """错误类型枚举"""
    ELEMENT_NOT_FOUND = "element_not_found"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    PAGE_LOAD_ERROR = "page_load_error"
    JAVASCRIPT_ERROR = "javascript_error"
    SELECTOR_INVALID = "selector_invalid"
    PERMISSION_DENIED = "permission_denied"
    UNKNOWN = "unknown"


class ErrorSeverity(str, Enum):
    """错误严重程度"""
    LOW = "low"           # 可能自愈
    MEDIUM = "medium"     # 需要AI干预
    HIGH = "high"         # 需要人工处理
    CRITICAL = "critical" # 无法自愈


class HealingStatus(str, Enum):
    """自愈状态"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ErrorContext(BaseModel):
    """错误上下文信息"""
    error_id: str = Field(..., description="错误唯一标识")
    timestamp: datetime = Field(default_factory=datetime.now, description="错误发生时间")
    
    # 错误基本信息
    error_type: ErrorType = Field(..., description="错误类型")
    error_message: str = Field(..., description="错误消息")
    error_details: Optional[str] = Field(None, description="详细错误信息")
    severity: ErrorSeverity = Field(..., description="错误严重程度")
    
    # 执行上下文
    workflow_path: str = Field(..., description="工作流文件路径")
    step_index: int = Field(..., description="失败步骤索引")
    step_data: Dict[str, Any] = Field(..., description="失败步骤数据")
    
    # 页面状态
    page_url: Optional[str] = Field(None, description="页面URL")
    page_title: Optional[str] = Field(None, description="页面标题")
    screenshot_path: Optional[str] = Field(None, description="截图路径")
    dom_snapshot: Optional[str] = Field(None, description="DOM快照路径")
    
    # 浏览器状态
    browser_type: Optional[str] = Field(None, description="浏览器类型")
    viewport_size: Optional[Dict[str, int]] = Field(None, description="视口大小")
    user_agent: Optional[str] = Field(None, description="用户代理")
    
    # 环境信息
    execution_context: Optional[Dict[str, Any]] = Field(None, description="执行上下文变量")
    retry_count: int = Field(0, description="重试次数")
    
    # 自愈相关
    is_healable: Optional[bool] = Field(None, description="是否可自愈")
    healing_status: HealingStatus = Field(HealingStatus.NOT_STARTED, description="自愈状态")
    healing_attempts: int = Field(0, description="自愈尝试次数")
    
    class Config:
        use_enum_values = True


class FailurePoint(BaseModel):
    """失败点信息"""
    step_index: int = Field(..., description="失败步骤索引")
    step_type: str = Field(..., description="步骤类型")
    selector: Optional[str] = Field(None, description="选择器")
    action: Optional[str] = Field(None, description="操作类型")
    target_element: Optional[str] = Field(None, description="目标元素描述")
    expected_state: Optional[Dict[str, Any]] = Field(None, description="期望状态")
    actual_state: Optional[Dict[str, Any]] = Field(None, description="实际状态")


class HealingAction(BaseModel):
    """自愈操作记录"""
    action_id: str = Field(..., description="操作唯一标识")
    timestamp: datetime = Field(default_factory=datetime.now, description="操作时间")
    action_type: str = Field(..., description="操作类型")
    selector: Optional[str] = Field(None, description="选择器")
    value: Optional[str] = Field(None, description="操作值")
    coordinates: Optional[Dict[str, float]] = Field(None, description="坐标信息")
    description: str = Field(..., description="操作描述")
    success: bool = Field(..., description="操作是否成功")
    
    class Config:
        use_enum_values = True


class HealingSession(BaseModel):
    """自愈会话信息"""
    session_id: str = Field(..., description="会话唯一标识")
    error_context: ErrorContext = Field(..., description="错误上下文")
    start_time: datetime = Field(default_factory=datetime.now, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    
    # 自愈过程
    healing_goal: str = Field(..., description="自愈目标")
    healing_actions: List[HealingAction] = Field(default_factory=list, description="自愈操作列表")
    
    # 结果信息
    status: HealingStatus = Field(HealingStatus.NOT_STARTED, description="会话状态")
    success: bool = Field(False, description="是否成功")
    failure_reason: Optional[str] = Field(None, description="失败原因")
    
    # 生成的步骤
    new_steps: List[Dict[str, Any]] = Field(default_factory=list, description="生成的新步骤")
    
    class Config:
        use_enum_values = True


class ValidationResult(BaseModel):
    """验证结果"""
    is_valid: bool = Field(..., description="是否有效")
    errors: List[str] = Field(default_factory=list, description="错误列表")
    warnings: List[str] = Field(default_factory=list, description="警告列表")
    score: float = Field(0.0, description="验证分数 (0-1)")
    
    
class HealingHistory(BaseModel):
    """自愈历史记录"""
    workflow_path: str = Field(..., description="工作流路径")
    error_patterns: List[str] = Field(default_factory=list, description="错误模式")
    healing_sessions: List[HealingSession] = Field(default_factory=list, description="自愈会话列表")
    success_rate: float = Field(0.0, description="成功率")
    last_updated: datetime = Field(default_factory=datetime.now, description="最后更新时间")
    
    class Config:
        use_enum_values = True 