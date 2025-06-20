"""录制命令实现"""
import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table

from ..core.recorder import WorkflowRecorder
from ..utils.cleaner import ScriptCleaner
from ..utils.logger import logger

console = Console()


async def record_workflow(
    name: str,
    description: str = "",
    output: str = "./workflows/",
    headless: bool = False,
    interactive: bool = True,
    auto_clean: bool = True
) -> None:
    """录制工作流
    
    Args:
        name: 工作流名称
        description: 工作流描述
        output: 输出目录
        headless: 是否无头模式
        interactive: 是否交互式录制
        auto_clean: 是否自动清理
    """
    recorder = WorkflowRecorder(output_dir=output)
    
    try:
        console.print(f"[bold green]开始录制工作流: {name}[/bold green]")
        console.print(f"描述: {description}")
        console.print(f"输出目录: {output}")
        console.print(f"模式: {'交互式' if interactive else '引导式'}")
        
        if interactive:
            # 交互式录制
            workflow = await recorder.interactive_recording(name, description)
            
            console.print("\n[yellow]🎬 录制已启动！[/yellow]")
            console.print("请在打开的浏览器中进行您的操作...")
            console.print("完成后按 [bold]Enter[/bold] 键停止录制")
            
            # 等待用户输入
            input()
            
        else:
            # 引导式录制
            task_description = Prompt.ask("请描述您希望自动化的任务")
            workflow = await recorder.guided_recording(name, task_description)
        
        # 停止录制
        workflow = await recorder.stop_recording(save=True)
        
        if workflow and len(workflow.steps) > 0:
            console.print(f"\n[green]✅ 录制完成！[/green]")
            console.print(f"步骤数量: {len(workflow.steps)}")
            
            # 显示录制的步骤
            _display_workflow_steps(workflow)
            
            # 询问是否清理工作流
            if auto_clean or Confirm.ask("是否要清理和优化工作流？"):
                await _clean_workflow(workflow, output)
            
        else:
            console.print("[yellow]⚠️ 没有录制到任何步骤[/yellow]")
            
    except Exception as e:
        console.print(f"[red]❌ 录制失败: {e}[/red]")
        logger.error("录制工作流失败", error=str(e))
        raise typer.Exit(1)


async def _clean_workflow(workflow, output_dir: str) -> None:
    """清理工作流"""
    console.print("\n[yellow]🧹 正在清理工作流...[/yellow]")
    
    cleaner = ScriptCleaner()
    cleaned_workflow = cleaner.clean_workflow(workflow)
    
    # 保存清理后的工作流
    output_path = Path(output_dir) / f"{cleaned_workflow.name}_cleaned.json"
    cleaned_workflow.save_to_file(output_path)
    
    # 显示优化报告
    report = cleaner.get_optimization_report()
    
    console.print(f"[green]✅ 清理完成！[/green]")
    console.print(f"原始步骤: {len(workflow.steps)}")
    console.print(f"清理后步骤: {len(cleaned_workflow.steps)}")
    console.print(f"优化次数: {report['total_optimizations']}")
    
    if report['recommendations']:
        console.print("\n[bold]优化建议:[/bold]")
        for rec in report['recommendations']:
            console.print(f"• {rec}")


def _display_workflow_steps(workflow) -> None:
    """显示工作流步骤"""
    table = Table(title=f"工作流步骤: {workflow.name}")
    table.add_column("步骤", style="cyan")
    table.add_column("类型", style="magenta")
    table.add_column("描述", style="green")
    table.add_column("目标", style="yellow")
    
    for i, step in enumerate(workflow.steps, 1):
        target = ""
        if step.url:
            target = step.url
        elif step.selector:
            target = step.selector
        elif step.value:
            target = step.value
        
        table.add_row(
            str(i),
            step.type.value,
            step.description or "-",
            target[:50] + "..." if len(target) > 50 else target
        )
    
    console.print(table)


async def list_workflows(output_dir: str = "./workflows/") -> None:
    """列出所有工作流"""
    recorder = WorkflowRecorder(output_dir=output_dir)
    workflows = recorder.list_workflows()
    
    if not workflows:
        console.print("[yellow]没有找到任何工作流[/yellow]")
        return
    
    table = Table(title="已保存的工作流")
    table.add_column("名称", style="cyan")
    table.add_column("描述", style="green")
    table.add_column("版本", style="magenta")
    table.add_column("步骤数", style="yellow")
    table.add_column("创建时间", style="blue")
    
    for workflow in workflows:
        table.add_row(
            workflow["name"],
            workflow["description"][:30] + "..." if len(workflow["description"]) > 30 else workflow["description"],
            workflow["version"],
            str(workflow["steps_count"]),
            workflow["created_at"].strftime("%Y-%m-%d %H:%M") if workflow["created_at"] else "-"
        )
    
    console.print(table)


async def show_workflow(name: str, output_dir: str = "./workflows/") -> None:
    """显示工作流详情"""
    recorder = WorkflowRecorder(output_dir=output_dir)
    workflow = recorder.load_workflow(name)
    
    if not workflow:
        console.print(f"[red]工作流 '{name}' 不存在[/red]")
        raise typer.Exit(1)
    
    console.print(f"\n[bold]工作流: {workflow.name}[/bold]")
    console.print(f"描述: {workflow.description}")
    console.print(f"版本: {workflow.version}")
    console.print(f"创建时间: {workflow.created_at}")
    console.print(f"更新时间: {workflow.updated_at}")
    
    if workflow.variables:
        console.print("\n[bold]变量:[/bold]")
        for var_name, var in workflow.variables.items():
            console.print(f"• {var_name}: {var.type} = {var.default} ({var.description})")
    
    _display_workflow_steps(workflow)


# 为了支持异步函数，需要包装器
def record_command(
    name: str = typer.Option(..., "--name", "-n", help="工作流名称"),
    description: str = typer.Option("", "--description", "-d", help="工作流描述"),
    output: str = typer.Option("./workflows/", "--output", "-o", help="输出目录"),
    headless: bool = typer.Option(False, "--headless", help="无头模式"),
    interactive: bool = typer.Option(True, "--interactive/--guided", help="交互式/引导式录制"),
    auto_clean: bool = typer.Option(True, "--auto-clean/--no-clean", help="自动清理")
):
    """录制新的工作流"""
    asyncio.run(record_workflow(name, description, output, headless, interactive, auto_clean))


def list_command(
    output: str = typer.Option("./workflows/", "--output", "-o", help="工作流目录")
):
    """列出所有工作流"""
    asyncio.run(list_workflows(output))


def show_command(
    name: str = typer.Argument(..., help="工作流名称"),
    output: str = typer.Option("./workflows/", "--output", "-o", help="工作流目录")
):
    """显示工作流详情"""
    asyncio.run(show_workflow(name, output))
