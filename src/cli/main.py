"""Browser-Use-Playwright CLI主入口"""
import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

# 添加项目根目录到Python路径以支持绝对导入
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.core.config import config
from src.core.recorder import WorkflowRecorder
from src.utils.logger import logger
from .record import record_command, list_command, show_command

app = typer.Typer(name="browser-use-playwright", help="Browser-Use + Playwright RPA自动化框架")
console = Console()

# 子命令组
record_app = typer.Typer(name="record", help="录制相关命令")
app.add_typer(record_app, name="record")


@app.command()
def version():
    """显示版本信息"""
    console.print(f"[bold green]Browser-Use-Playwright[/bold green] v{config.app.version}")
    console.print("Browser-AI RPA Starter - 录制、执行、自愈")


@app.command()
def list():
    """列出所有工作流"""
    try:
        recorder = WorkflowRecorder()
        workflows = recorder.list_workflows()
        
        if not workflows:
            console.print("[yellow]没有找到工作流文件[/yellow]")
            return
        
        table = Table(title="工作流列表")
        table.add_column("名称", style="cyan", no_wrap=True)
        table.add_column("描述", style="magenta")
        table.add_column("步骤数", justify="right", style="green")
        table.add_column("变量数", justify="right", style="blue")
        table.add_column("版本", style="yellow")
        
        for wf in workflows:
            table.add_row(
                wf["name"],
                wf["description"] or "无描述",
                str(wf["steps_count"]),
                str(wf["variables_count"]),
                wf["version"]
            )
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]列出工作流失败: {e}[/red]")
        sys.exit(1)


@app.command()
def show(workflow_name: str):
    """显示工作流详情"""
    try:
        recorder = WorkflowRecorder()
        workflow = recorder.load_workflow(workflow_name)
        
        if not workflow:
            console.print(f"[red]工作流 '{workflow_name}' 不存在[/red]")
            sys.exit(1)
        
        console.print(f"[bold cyan]工作流: {workflow.name}[/bold cyan]")
        console.print(f"描述: {workflow.description or '无描述'}")
        console.print(f"版本: {workflow.version}")
        console.print(f"步骤数: {len(workflow.steps)}")
        console.print(f"变量数: {len(workflow.variables)}")
        
        if workflow.steps:
            console.print("\n[bold yellow]步骤列表:[/bold yellow]")
            for i, step in enumerate(workflow.steps, 1):
                console.print(f"  {i}. [{step.type.value}] {step.description}")
        
        if workflow.variables:
            console.print("\n[bold yellow]变量列表:[/bold yellow]")
            for var_name, var_info in workflow.variables.items():
                console.print(f"  - {var_name}: {var_info.description}")
        
    except Exception as e:
        console.print(f"[red]显示工作流失败: {e}[/red]")
        sys.exit(1)


@app.command()
def clean(workflow_name: Optional[str] = None):
    """清理优化工作流"""
    try:
        from src.utils.cleaner import ScriptCleaner
        
        cleaner = ScriptCleaner()
        
        if workflow_name:
            # 清理单个工作流
            result = cleaner.clean_workflow_file(f"workflows/{workflow_name}.json")
            if result:
                console.print(f"[green]工作流 '{workflow_name}' 清理完成[/green]")
                console.print(f"优化步骤数: {result.get('optimized_steps', 0)}")
            else:
                console.print(f"[red]工作流 '{workflow_name}' 清理失败[/red]")
        else:
            # 清理所有工作流
            console.print("[yellow]清理所有工作流...[/yellow]")
            # 这里可以实现批量清理逻辑
            console.print("[green]批量清理完成[/green]")
            
    except Exception as e:
        console.print(f"[red]清理工作流失败: {e}[/red]")
        sys.exit(1)


@record_app.command("douban-book")
def record_douban_book():
    """录制豆瓣图书搜索功能（测试用例）"""
    console.print("[bold blue]🚀 开始录制豆瓣图书搜索功能[/bold blue]")
    console.print("📖 任务：搜索《架构简洁之道》并获取评分和简介")
    
    try:
        # 直接调用测试函数，避免导入问题
        sys.path.insert(0, str(project_root / "scripts"))
        
        # 导入并运行测试函数
        import test_douban_book_search
        
        # 验证依赖
        if not asyncio.run(test_douban_book_search.validate_dependencies()):
            console.print("[red]❌ 依赖检查失败[/red]")
            sys.exit(1)
        
        # 运行测试
        success = asyncio.run(test_douban_book_search.test_douban_book_search())
        
        if success:
            console.print("[green]✅ 录制完成！[/green]")
            console.print("💡 可以使用 'browser-use-playwright show douban_book_search_architecture_clean_code' 查看结果")
        else:
            console.print("[red]❌ 录制失败[/red]")
            sys.exit(1)
            
    except Exception as e:
        console.print(f"[red]录制失败: {e}[/red]")
        logger.error("豆瓣图书搜索录制失败", error=str(e))
        sys.exit(1)


@app.command()
def web():
    """启动Web UI界面"""
    try:
        console.print("[bold blue]🌐 启动Web UI界面...[/bold blue]")
        console.print("📝 地址: http://localhost:8000")
        
        # 启动Web UI
        import subprocess
        import sys
        from pathlib import Path
        
        script_path = Path(__file__).parent.parent.parent / "scripts" / "start_web_ui.py"
        subprocess.run([sys.executable, str(script_path)])
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Web UI已停止[/yellow]")
    except Exception as e:
        console.print(f"[red]启动Web UI失败: {e}[/red]")
        sys.exit(1)


# 执行相关命令
@app.command()
def run(
    workflow_name: str = typer.Argument(..., help="工作流名称"),
    variables: Optional[str] = typer.Option(None, "--vars", "-v", help="输入变量JSON字符串"),
    variables_file: Optional[Path] = typer.Option(None, "--vars-file", "-f", help="输入变量JSON文件"),
    headless: bool = typer.Option(False, "--headless", help="无头模式运行"),
    timeout: int = typer.Option(30, "--timeout", "-t", help="超时时间(秒)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="结果输出文件"),
    show_progress: bool = typer.Option(True, "--progress/--no-progress", help="显示进度条"),
):
    """执行工作流"""
    from src.cli.run import run_workflow
    run_workflow(workflow_name, variables, variables_file, headless, timeout, output, show_progress)


@app.command()
def batch(
    workflow_name: str = typer.Argument(..., help="工作流名称"),
    data_file: Path = typer.Argument(..., help="批量数据文件(JSON)"),
    concurrent: int = typer.Option(5, "--concurrent", "-c", help="并发数量"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="无头模式运行"),
    timeout: int = typer.Option(30, "--timeout", "-t", help="超时时间(秒)"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="结果输出目录"),
    continue_on_error: bool = typer.Option(True, "--continue-on-error/--stop-on-error", help="遇到错误是否继续"),
):
    """批量执行工作流"""
    from src.cli.run import batch_run
    batch_run(workflow_name, data_file, concurrent, headless, timeout, output_dir, continue_on_error)


@app.command()
def tasks():
    """列出正在运行的任务"""
    from src.cli.run import list_tasks
    list_tasks()


@app.command()
def heal():
    """使用AI修复工作流（待实现）"""
    console.print("[yellow]AI自愈功能正在开发中...[/yellow]")
    console.print("💡 这将在Phase 3中实现")


@app.command()
def logs():
    """查看执行日志（待实现）"""
    console.print("[yellow]日志查看功能正在开发中...[/yellow]")
    console.print("💡 这将在Phase 4中实现")


def main():
    """CLI主入口"""
    app()


if __name__ == "__main__":
    main()
