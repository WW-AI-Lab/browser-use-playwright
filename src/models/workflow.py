"""工作流数据模型"""
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class StepType(str, Enum):
    """步骤类型枚举"""
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    WAIT = "wait"
    SCROLL = "scroll"
    HOVER = "hover"
    PRESS_KEY = "press_key"
    SCREENSHOT = "screenshot"
    EXTRACT = "extract"
    CUSTOM = "custom"


class WorkflowStep(BaseModel):
    """工作流步骤"""
    id: str = Field(..., description="步骤唯一标识")
    type: StepType = Field(..., description="步骤类型")
    description: str = Field("", description="步骤描述")
    
    # 通用属性
    selector: Optional[str] = Field(None, description="CSS选择器")
    xpath: Optional[str] = Field(None, description="XPath选择器")
    url: Optional[str] = Field(None, description="目标URL")
    value: Optional[str] = Field(None, description="输入值或文本")
    timeout: Optional[int] = Field(None, description="超时时间(毫秒)")
    
    # 特殊属性
    key: Optional[str] = Field(None, description="按键名称")
    scroll_direction: Optional[str] = Field(None, description="滚动方向")
    scroll_amount: Optional[int] = Field(None, description="滚动距离")
    wait_condition: Optional[str] = Field(None, description="等待条件")
    
    # 元数据
    screenshot_path: Optional[str] = Field(None, description="截图路径")
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")


class WorkflowVariable(BaseModel):
    """工作流变量"""
    name: str = Field(..., description="变量名称")
    type: str = Field("string", description="变量类型")
    description: str = Field("", description="变量描述")
    default: Optional[Any] = Field(None, description="默认值")
    required: bool = Field(False, description="是否必填")
    options: Optional[List[str]] = Field(None, description="可选值列表")


class Workflow(BaseModel):
    """工作流模型"""
    name: str = Field(..., description="工作流名称")
    description: str = Field("", description="工作流描述")
    version: str = Field("1.0.0", description="版本号")
    
    # 步骤和变量
    steps: List[WorkflowStep] = Field(default_factory=list, description="步骤列表")
    variables: Dict[str, WorkflowVariable] = Field(default_factory=dict, description="变量定义")
    
    # 配置
    timeout: int = Field(30000, description="默认超时时间(毫秒)")
    retry_count: int = Field(3, description="重试次数")
    parallel: bool = Field(False, description="是否支持并行执行")
    
    # 元数据
    tags: List[str] = Field(default_factory=list, description="标签")
    author: str = Field("", description="作者")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    def add_step(self, step: WorkflowStep) -> None:
        """添加步骤"""
        self.steps.append(step)
        self.updated_at = datetime.now()
    
    def add_variable(self, variable: WorkflowVariable) -> None:
        """添加变量"""
        self.variables[variable.name] = variable
        self.updated_at = datetime.now()
    
    def get_step_by_id(self, step_id: str) -> Optional[WorkflowStep]:
        """根据ID获取步骤"""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None
    
    def remove_step(self, step_id: str) -> bool:
        """删除步骤"""
        for i, step in enumerate(self.steps):
            if step.id == step_id:
                del self.steps[i]
                self.updated_at = datetime.now()
                return True
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.model_dump()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Workflow":
        """从字典创建工作流"""
        return cls(**data)
    
    def save_to_file(self, file_path: Union[str, Path]) -> None:
        """保存到文件"""
        import json
        
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2, default=str)
    
    @classmethod
    def load_from_file(cls, file_path: Union[str, Path]) -> "Workflow":
        """从文件加载工作流"""
        import json
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return cls.from_dict(data)
