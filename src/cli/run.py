"""运行工作流命令"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.json import JSON

from src.core.executor import PlaywrightExecutor, task_manager
from src.core.recorder import WorkflowRecorder
from src.models.workflow import Workflow
from src.models.result import ExecutionStatus
from src.utils.logger import logger

console = Console()


def run_workflow(
    workflow_name: str = typer.Argument(..., help="工作流名称"),
    variables: Optional[str] = typer.Option(None, "--vars", "-v", help="输入变量JSON字符串"),
    variables_file: Optional[Path] = typer.Option(None, "--vars-file", "-f", help="输入变量JSON文件"),
    headless: bool = typer.Option(False, "--headless", help="无头模式运行"),
    timeout: int = typer.Option(30, "--timeout", "-t", help="超时时间(秒)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="结果输出文件"),
    show_progress: bool = typer.Option(True, "--progress/--no-progress", help="显示进度条"),
) -> None:
    """运行工作流"""
    
    console.print(f"🚀 开始执行工作流: [bold cyan]{workflow_name}[/bold cyan]")
    
    try:
        # 加载工作流
        recorder = WorkflowRecorder()
        workflow = recorder.load_workflow(workflow_name)
        
        if not workflow:
            console.print(f"❌ 工作流不存在: {workflow_name}", style="red")
            raise typer.Exit(1)
        
        # 解析输入变量
        input_variables = {}
        
        if variables:
            try:
                input_variables.update(json.loads(variables))
            except json.JSONDecodeError as e:
                console.print(f"❌ 变量JSON格式错误: {e}", style="red")
                raise typer.Exit(1)
        
        if variables_file:
            try:
                with open(variables_file, 'r', encoding='utf-8') as f:
                    file_vars = json.load(f)
                    input_variables.update(file_vars)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                console.print(f"❌ 变量文件错误: {e}", style="red")
                raise typer.Exit(1)
        
        # 显示执行信息
        info_table = Table(title="执行信息")
        info_table.add_column("项目", style="cyan")
        info_table.add_column("值", style="green")
        
        info_table.add_row("工作流名称", workflow_name)
        info_table.add_row("步骤数量", str(len(workflow.steps)))
        info_table.add_row("变量数量", str(len(workflow.variables)))
        info_table.add_row("输入变量", str(len(input_variables)))
        info_table.add_row("无头模式", "是" if headless else "否")
        info_table.add_row("超时时间", f"{timeout}秒")
        
        console.print(info_table)
        
        # 验证必需变量
        missing_vars = []
        for var_name, var_def in workflow.variables.items():
            if var_def.required and var_name not in input_variables:
                if var_def.default is None:
                    missing_vars.append(var_name)
        
        if missing_vars:
            console.print(f"❌ 缺少必需变量: {', '.join(missing_vars)}", style="red")
            raise typer.Exit(1)
        
        # 执行工作流
        console.print("\n📋 开始执行工作流...")
        
        result = asyncio.run(_execute_workflow_async(
            workflow, input_variables, headless, timeout, show_progress
        ))
        
        # 显示执行结果
        _display_execution_result(result)
        
        # 保存结果到文件
        if output:
            _save_result_to_file(result, output)
            console.print(f"📄 结果已保存到: {output}")
        
        # 根据执行结果设置退出码
        if result.is_successful:
            console.print("✅ 工作流执行成功!", style="green")
        else:
            console.print("❌ 工作流执行失败!", style="red")
            raise typer.Exit(1)
            
    except Exception as e:
        logger.error("执行工作流时出错", error=str(e))
        console.print(f"❌ 执行失败: {e}", style="red")
        raise typer.Exit(1)


def batch_run(
    workflow_name: str = typer.Argument(..., help="工作流名称"),
    data_file: Path = typer.Argument(..., help="批量数据文件(JSON)"),
    concurrent: int = typer.Option(5, "--concurrent", "-c", help="并发数量"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="无头模式运行"),
    timeout: int = typer.Option(30, "--timeout", "-t", help="超时时间(秒)"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="结果输出目录"),
    continue_on_error: bool = typer.Option(True, "--continue-on-error/--stop-on-error", help="遇到错误是否继续"),
) -> None:
    """批量运行工作流"""
    
    console.print(f"🚀 开始批量执行工作流: [bold cyan]{workflow_name}[/bold cyan]")
    
    try:
        # 加载工作流
        recorder = WorkflowRecorder()
        workflow = recorder.load_workflow(workflow_name)
        
        if not workflow:
            console.print(f"❌ 工作流不存在: {workflow_name}", style="red")
            raise typer.Exit(1)
        
        # 加载批量数据
        if not data_file.exists():
            console.print(f"❌ 数据文件不存在: {data_file}", style="red")
            raise typer.Exit(1)
        
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                input_data_list = json.load(f)
        except json.JSONDecodeError as e:
            console.print(f"❌ 数据文件JSON格式错误: {e}", style="red")
            raise typer.Exit(1)
        
        if not isinstance(input_data_list, list):
            console.print("❌ 数据文件必须包含JSON数组", style="red")
            raise typer.Exit(1)
        
        # 显示批量执行信息
        info_table = Table(title="批量执行信息")
        info_table.add_column("项目", style="cyan")
        info_table.add_column("值", style="green")
        
        info_table.add_row("工作流名称", workflow_name)
        info_table.add_row("数据条数", str(len(input_data_list)))
        info_table.add_row("并发数量", str(concurrent))
        info_table.add_row("无头模式", "是" if headless else "否")
        info_table.add_row("超时时间", f"{timeout}秒")
        
        console.print(info_table)
        
        # 执行批量任务
        console.print("\n📋 开始批量执行...")
        
        batch_result = asyncio.run(_execute_batch_async(
            workflow, input_data_list, concurrent, headless, timeout
        ))
        
        # 显示批量执行结果
        _display_batch_result(batch_result)
        
        # 保存结果到目录
        if output_dir:
            _save_batch_results(batch_result, output_dir)
            console.print(f"📁 批量结果已保存到: {output_dir}")
        
        # 根据执行结果设置退出码
        if batch_result.success_rate > 0.5:  # 成功率超过50%算成功
            console.print(f"✅ 批量执行完成! 成功率: {batch_result.success_rate:.1%}", style="green")
        else:
            console.print(f"❌ 批量执行失败! 成功率: {batch_result.success_rate:.1%}", style="red")
            if not continue_on_error:
                raise typer.Exit(1)
            
    except Exception as e:
        logger.error("批量执行工作流时出错", error=str(e))
        console.print(f"❌ 批量执行失败: {e}", style="red")
        raise typer.Exit(1)


def list_tasks() -> None:
    """列出正在运行的任务"""
    
    console.print("📋 正在运行的任务:")
    
    active_tasks = task_manager.get_active_tasks()
    
    if not active_tasks:
        console.print("没有正在运行的任务", style="yellow")
        return
    
    table = Table()
    table.add_column("任务ID", style="cyan")
    table.add_column("工作流", style="green")
    table.add_column("状态", style="yellow")
    table.add_column("开始时间", style="blue")
    table.add_column("批次大小", style="magenta")
    
    for task_id, info in active_tasks.items():
        batch_size = str(info.get('batch_size', '-'))
        table.add_row(
            task_id,
            info['workflow_name'],
            info['status'],
            info['start_time'].strftime('%H:%M:%S'),
            batch_size
        )
    
    console.print(table)


async def _execute_workflow_async(
    workflow: Workflow,
    input_variables: Dict[str, Any],
    headless: bool,
    timeout: int,
    show_progress: bool
) -> Any:
    """异步执行工作流"""
    
    executor = PlaywrightExecutor(
        headless=headless,
        timeout=timeout
    )
    
    try:
        if show_progress:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True
            ) as progress:
                task = progress.add_task("执行工作流...", total=None)
                
                result = await executor.execute_workflow(workflow, input_variables)
                
                progress.update(task, description="执行完成")
                
                return result
        else:
            return await executor.execute_workflow(workflow, input_variables)
            
    finally:
        await executor.cleanup()


async def _execute_batch_async(
    workflow: Workflow,
    input_data_list: List[Dict[str, Any]],
    concurrent: int,
    headless: bool,
    timeout: int
) -> Any:
    """异步批量执行工作流"""
    
    executor = PlaywrightExecutor(
        headless=headless,
        timeout=timeout
    )
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task(f"批量执行 {len(input_data_list)} 个任务...", total=None)
            
            result = await executor.execute_batch(
                workflow, input_data_list, concurrent
            )
            
            progress.update(task, description="批量执行完成")
            
            return result
            
    finally:
        await executor.cleanup()


def _display_execution_result(result) -> None:
    """显示执行结果"""
    
    # 基本信息
    status_color = "green" if result.is_successful else "red"
    status_icon = "✅" if result.is_successful else "❌"
    
    console.print(f"\n{status_icon} 执行状态: [{status_color}]{result.status.value}[/{status_color}]")
    console.print(f"⏱️  执行时长: {result.duration:.2f}秒")
    console.print(f"📊 成功率: {result.success_rate:.1%}")
    
    # 步骤结果表格
    if result.step_results:
        table = Table(title="步骤执行结果")
        table.add_column("步骤", style="cyan")
        table.add_column("类型", style="blue")
        table.add_column("状态", style="yellow")
        table.add_column("时长(秒)", style="magenta")
        table.add_column("错误", style="red")
        
        for i, step_result in enumerate(result.step_results, 1):
            status_style = "green" if step_result.is_successful else "red"
            duration = f"{step_result.duration:.2f}" if step_result.duration else "-"
            error = step_result.error_message[:50] + "..." if step_result.error_message and len(step_result.error_message) > 50 else (step_result.error_message or "-")
            
            table.add_row(
                str(i),
                step_result.step_type,
                f"[{status_style}]{step_result.status.value}[/{status_style}]",
                duration,
                error
            )
        
        console.print(table)
    
    # 输出变量
    if result.output_variables:
        console.print("\n📤 输出变量:")
        console.print(JSON.from_data(result.output_variables))


def _display_batch_result(batch_result) -> None:
    """显示批量执行结果"""
    
    # 基本信息
    status_color = "green" if batch_result.success_rate > 0.5 else "red"
    
    console.print(f"\n📊 批量执行统计:")
    console.print(f"总任务数: {batch_result.total_executions}")
    console.print(f"成功任务: {batch_result.successful_executions}")
    console.print(f"失败任务: {batch_result.failed_executions}")
    console.print(f"[{status_color}]成功率: {batch_result.success_rate:.1%}[/{status_color}]")
    console.print(f"⏱️  总时长: {batch_result.duration:.2f}秒")
    
    # 失败任务详情
    failed_results = [r for r in batch_result.execution_results if not r.is_successful]
    if failed_results:
        console.print(f"\n❌ 失败任务详情 ({len(failed_results)}个):")
        
        table = Table()
        table.add_column("执行ID", style="cyan")
        table.add_column("错误信息", style="red")
        table.add_column("失败步骤", style="yellow")
        
        for result in failed_results[:10]:  # 只显示前10个失败任务
            table.add_row(
                result.execution_id,
                (result.error_message[:60] + "...") if result.error_message and len(result.error_message) > 60 else (result.error_message or "-"),
                result.failed_step_id or "-"
            )
        
        console.print(table)
        
        if len(failed_results) > 10:
            console.print(f"... 还有 {len(failed_results) - 10} 个失败任务")


def _save_result_to_file(result, output_path: Path) -> None:
    """保存执行结果到文件"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    result_data = result.model_dump()
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2, default=str)


def _save_batch_results(batch_result, output_dir: Path) -> None:
    """保存批量执行结果"""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存总结果
    summary_file = output_dir / "batch_summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(batch_result.model_dump(), f, ensure_ascii=False, indent=2, default=str)
    
    # 保存各个执行结果
    results_dir = output_dir / "individual_results"
    results_dir.mkdir(exist_ok=True)
    
    for result in batch_result.execution_results:
        result_file = results_dir / f"{result.execution_id}.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result.model_dump(), f, ensure_ascii=False, indent=2, default=str)
