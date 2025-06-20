#!/usr/bin/env python3
"""创建示例工作流的脚本"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.models.workflow import Workflow, WorkflowStep, WorkflowVariable, StepType
from src.core.recorder import WorkflowRecorder

def create_sample_workflows():
    """创建示例工作流"""
    recorder = WorkflowRecorder()
    
    # 创建Google搜索工作流
    google_search = Workflow(
        name="google_search",
        description="在Google上搜索指定关键词",
        version="1.0.0"
    )
    
    # 添加变量
    search_var = WorkflowVariable(
        name="search_query",
        type="string",
        description="搜索关键词",
        default="Browser-Use-Playwright",
        required=True
    )
    google_search.add_variable(search_var)
    
    # 添加步骤
    steps = [
        WorkflowStep(
            id="step_1",
            type=StepType.NAVIGATE,
            url="https://www.google.com",
            description="打开Google首页"
        ),
        WorkflowStep(
            id="step_2",
            type=StepType.FILL,
            selector="input[name='q']",
            value="{{ search_query }}",
            description="输入搜索关键词"
        ),
        WorkflowStep(
            id="step_3",
            type=StepType.PRESS_KEY,
            key="Enter",
            description="按Enter键搜索"
        ),
        WorkflowStep(
            id="step_4",
            type=StepType.WAIT,
            selector="#search",
            timeout=5000,
            wait_condition="visible",
            description="等待搜索结果加载"
        ),
        WorkflowStep(
            id="step_5",
            type=StepType.SCREENSHOT,
            description="截取搜索结果页面"
        )
    ]
    
    for step in steps:
        google_search.add_step(step)
    
    # 保存工作流
    google_search.save_to_file(recorder.output_dir / "google_search.json")
    print(f"✅ 创建示例工作流: {google_search.name}")
    
    # 创建登录工作流
    login_flow = Workflow(
        name="login_demo",
        description="演示登录流程",
        version="1.0.0"
    )
    
    # 添加变量
    username_var = WorkflowVariable(
        name="username",
        type="string",
        description="用户名",
        default="demo@example.com",
        required=True
    )
    password_var = WorkflowVariable(
        name="password",
        type="string",
        description="密码",
        default="password123",
        required=True
    )
    
    login_flow.add_variable(username_var)
    login_flow.add_variable(password_var)
    
    # 添加步骤
    login_steps = [
        WorkflowStep(
            id="login_1",
            type=StepType.NAVIGATE,
            url="https://example.com/login",
            description="打开登录页面"
        ),
        WorkflowStep(
            id="login_2",
            type=StepType.FILL,
            selector="#username",
            value="{{ username }}",
            description="输入用户名"
        ),
        WorkflowStep(
            id="login_3",
            type=StepType.FILL,
            selector="#password",
            value="{{ password }}",
            description="输入密码"
        ),
        WorkflowStep(
            id="login_4",
            type=StepType.CLICK,
            selector="button[type='submit']",
            description="点击登录按钮"
        ),
        WorkflowStep(
            id="login_5",
            type=StepType.WAIT,
            selector=".dashboard",
            timeout=10000,
            wait_condition="visible",
            description="等待登录成功后的仪表板"
        )
    ]
    
    for step in login_steps:
        login_flow.add_step(step)
    
    # 保存工作流
    login_flow.save_to_file(recorder.output_dir / "login_demo.json")
    print(f"✅ 创建示例工作流: {login_flow.name}")
    
    # 创建表单填写工作流
    form_fill = Workflow(
        name="form_fill_demo",
        description="演示表单填写流程",
        version="1.0.0"
    )
    
    # 添加变量
    form_vars = [
        WorkflowVariable(name="first_name", type="string", description="名字", default="张", required=True),
        WorkflowVariable(name="last_name", type="string", description="姓氏", default="三", required=True),
        WorkflowVariable(name="email", type="string", description="邮箱", default="zhangsan@example.com", required=True),
        WorkflowVariable(name="phone", type="string", description="电话", default="13800138000", required=False),
    ]
    
    for var in form_vars:
        form_fill.add_variable(var)
    
    # 添加步骤
    form_steps = [
        WorkflowStep(
            id="form_1",
            type=StepType.NAVIGATE,
            url="https://example.com/contact",
            description="打开联系表单页面"
        ),
        WorkflowStep(
            id="form_2",
            type=StepType.FILL,
            selector="input[name='firstName']",
            value="{{ first_name }}",
            description="填写名字"
        ),
        WorkflowStep(
            id="form_3",
            type=StepType.FILL,
            selector="input[name='lastName']",
            value="{{ last_name }}",
            description="填写姓氏"
        ),
        WorkflowStep(
            id="form_4",
            type=StepType.FILL,
            selector="input[name='email']",
            value="{{ email }}",
            description="填写邮箱"
        ),
        WorkflowStep(
            id="form_5",
            type=StepType.FILL,
            selector="input[name='phone']",
            value="{{ phone }}",
            description="填写电话"
        ),
        WorkflowStep(
            id="form_6",
            type=StepType.SELECT,
            selector="select[name='country']",
            value="CN",
            description="选择国家"
        ),
        WorkflowStep(
            id="form_7",
            type=StepType.CLICK,
            selector="button[type='submit']",
            description="提交表单"
        ),
        WorkflowStep(
            id="form_8",
            type=StepType.WAIT,
            selector=".success-message",
            timeout=5000,
            wait_condition="visible",
            description="等待成功提示"
        )
    ]
    
    for step in form_steps:
        form_fill.add_step(step)
    
    # 保存工作流
    form_fill.save_to_file(recorder.output_dir / "form_fill_demo.json")
    print(f"✅ 创建示例工作流: {form_fill.name}")
    
    print(f"\n🎉 总共创建了 3 个示例工作流!")
    print("你可以使用以下命令查看:")
    print("  python -m src.cli.main list")
    print("  python -m src.cli.main show google_search")
    print("  python -m src.cli.main web")

if __name__ == "__main__":
    create_sample_workflows() 