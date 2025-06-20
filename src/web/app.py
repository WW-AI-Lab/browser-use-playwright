"""Web UI应用 - 工作流查看和编辑界面"""
from pathlib import Path
from typing import Dict, List, Optional
import asyncio

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ..core.recorder import WorkflowRecorder
from ..core.executor import PlaywrightExecutor, task_manager
from ..core.browser_use_executor import HybridExecutor
from ..core.task_optimizer import task_optimizer, OptimizationResult
from ..models.workflow import Workflow, WorkflowStep, StepType
from ..models.result import ExecutionStatus, execution_history
from ..utils.cleaner import ScriptCleaner
from ..utils.logger import logger
from .template_manager import get_template_manager

# 创建FastAPI应用
app = FastAPI(
    title="Browser-Use-Playwright Web UI",
    description="工作流查看和编辑界面",
    version="1.0.0"
)

# 初始化模板管理器
template_manager = get_template_manager()
template_manager.ensure_directories()

# 设置模板目录
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# 设置静态文件目录
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 全局变量
recorder = WorkflowRecorder()
cleaner = ScriptCleaner()

# 添加录制任务管理
recording_tasks = {}


# Pydantic模型
class WorkflowUpdate(BaseModel):
    """工作流更新模型"""
    name: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[List[Dict]] = None


class StepUpdate(BaseModel):
    """步骤更新模型"""
    type: Optional[str] = None
    description: Optional[str] = None
    selector: Optional[str] = None
    xpath: Optional[str] = None
    url: Optional[str] = None
    value: Optional[str] = None
    timeout: Optional[int] = None


class ExecutionRequest(BaseModel):
    """执行请求模型"""
    variables: Optional[Dict] = None
    headless: bool = True
    timeout: int = 30


class RecordingRequest(BaseModel):
    """录制请求模型"""
    name: str
    description: str = ""
    task_description: str = ""
    headless: bool = False
    mode: str = "guided"  # "guided" or "interactive"
    auto_optimize: bool = True  # 是否自动优化任务描述


class TaskOptimizationRequest(BaseModel):
    """任务优化请求模型"""
    task_description: str
    language: str = "zh"  # 目标语言，默认中文


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """主页 - 工作流列表"""
    workflows = recorder.list_workflows()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "workflows": workflows
    })


@app.get("/api/workflows")
async def get_workflows():
    """获取所有工作流"""
    try:
        workflows = recorder.list_workflows()
        return {"workflows": workflows}
    except Exception as e:
        logger.error("获取工作流列表失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workflows/{workflow_name}")
async def get_workflow(workflow_name: str):
    """获取指定工作流"""
    try:
        workflow = recorder.load_workflow(workflow_name)
        if not workflow:
            raise HTTPException(status_code=404, detail="工作流不存在")
        
        return workflow.to_dict()
    except Exception as e:
        logger.error("获取工作流失败", workflow_name=workflow_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/workflows/{workflow_name}")
async def update_workflow(workflow_name: str, update_data: WorkflowUpdate):
    """更新工作流"""
    try:
        workflow = recorder.load_workflow(workflow_name)
        if not workflow:
            raise HTTPException(status_code=404, detail="工作流不存在")
        
        # 更新工作流属性
        if update_data.name:
            workflow.name = update_data.name
        if update_data.description is not None:
            workflow.description = update_data.description
        
        # 更新步骤
        if update_data.steps is not None:
            workflow.steps = []
            for step_data in update_data.steps:
                step = WorkflowStep(**step_data)
                workflow.steps.append(step)
        
        # 检查并转换工作流以确保兼容性
        if recorder.workflow_converter.needs_conversion(workflow):
            logger.info("更新后的工作流需要转换，开始自动转换", workflow_name=workflow.name)
            workflow = recorder.browser_use_converter.convert_workflow(workflow)
            logger.info("工作流已转换为兼容版本", workflow_name=workflow.name)
        
        # 保存更新后的工作流
        workflow.save_to_file(recorder.output_dir / f"{workflow.name}.json")
        
        logger.info("工作流更新成功", workflow_name=workflow.name)
        return {"message": "工作流更新成功", "workflow": workflow.to_dict()}
        
    except Exception as e:
        logger.error("更新工作流失败", workflow_name=workflow_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/workflows/{workflow_name}")
async def delete_workflow(workflow_name: str):
    """删除工作流"""
    try:
        workflow_file = recorder.output_dir / f"{workflow_name}.json"
        if not workflow_file.exists():
            raise HTTPException(status_code=404, detail="工作流不存在")
        
        workflow_file.unlink()
        logger.info("工作流删除成功", workflow_name=workflow_name)
        return {"message": "工作流删除成功"}
        
    except Exception as e:
        logger.error("删除工作流失败", workflow_name=workflow_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/workflows/{workflow_name}/clean")
async def clean_workflow(workflow_name: str):
    """清理工作流"""
    try:
        workflow = recorder.load_workflow(workflow_name)
        if not workflow:
            raise HTTPException(status_code=404, detail="工作流不存在")
        
        # 清理工作流
        cleaned_workflow = cleaner.clean_workflow(workflow)
        
        # 保存清理后的工作流
        output_path = recorder.output_dir / f"{workflow_name}_cleaned.json"
        cleaned_workflow.save_to_file(output_path)
        
        # 获取优化报告
        report = cleaner.get_optimization_report()
        
        logger.info("工作流清理成功", workflow_name=workflow_name)
        return {
            "message": "工作流清理成功",
            "cleaned_workflow": cleaned_workflow.to_dict(),
            "optimization_report": report
        }
        
    except Exception as e:
        logger.error("清理工作流失败", workflow_name=workflow_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/workflows/{workflow_name}/execute")
async def execute_workflow(workflow_name: str, execution_request: ExecutionRequest):
    """执行工作流"""
    try:
        workflow = recorder.load_workflow(workflow_name)
        if not workflow:
            raise HTTPException(status_code=404, detail="工作流不存在")
        
        # 提交执行任务
        task_id = await task_manager.submit_workflow_task(
            workflow=workflow,
            input_variables=execution_request.variables or {},
            task_id=f"web_{workflow_name}_{len(task_manager.active_tasks)}"
        )
        
        logger.info("工作流执行任务已提交", workflow_name=workflow_name, task_id=task_id)
        return {
            "message": "工作流执行任务已提交",
            "task_id": task_id,
            "status": "submitted"
        }
        
    except Exception as e:
        logger.error("提交工作流执行任务失败", workflow_name=workflow_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    """获取任务执行状态"""
    try:
        # 检查任务是否存在
        if task_id not in task_manager.active_tasks:
            # 可能已经完成，尝试获取结果
            result = await task_manager.get_task_result(task_id)
            if result:
                return {
                    "task_id": task_id,
                    "status": result.status.value,
                    "completed": True,
                    "result": result.model_dump()
                }
            else:
                raise HTTPException(status_code=404, detail="任务不存在")
        
        # 获取任务信息
        task_info = task_manager.active_tasks[task_id]
        
        # 尝试获取结果（如果已完成）
        result = await task_manager.get_task_result(task_id)
        if result:
            return {
                "task_id": task_id,
                "status": result.status.value,
                "completed": True,
                "result": result.model_dump()
            }
        
        # 任务仍在运行
        return {
            "task_id": task_id,
            "status": task_info["status"],
            "completed": False,
            "start_time": task_info["start_time"].isoformat()
        }
        
    except Exception as e:
        logger.error("获取任务状态失败", task_id=task_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """取消任务执行"""
    try:
        success = await task_manager.cancel_task(task_id)
        if success:
            logger.info("任务取消成功", task_id=task_id)
            return {"message": "任务取消成功", "task_id": task_id}
        else:
            raise HTTPException(status_code=404, detail="任务不存在或无法取消")
    except Exception as e:
        logger.error("取消任务失败", task_id=task_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tasks")
async def get_active_tasks():
    """获取所有活动任务"""
    try:
        tasks = task_manager.get_active_tasks()
        return {"tasks": tasks}
    except Exception as e:
        logger.error("获取活动任务失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workflows/{workflow_name}", response_class=HTMLResponse)
async def view_workflow(request: Request, workflow_name: str):
    """工作流详情页面"""
    try:
        workflow = recorder.load_workflow(workflow_name)
        if not workflow:
            raise HTTPException(status_code=404, detail="工作流不存在")
        
        return templates.TemplateResponse("workflow_detail.html", {
            "request": request,
            "workflow": workflow,
            "step_types": [step_type.value for step_type in StepType]
        })
        
    except Exception as e:
        logger.error("查看工作流失败", workflow_name=workflow_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workflows/{workflow_name}/edit", response_class=HTMLResponse)
async def edit_workflow(request: Request, workflow_name: str):
    """工作流编辑页面"""
    try:
        workflow = recorder.load_workflow(workflow_name)
        if not workflow:
            raise HTTPException(status_code=404, detail="工作流不存在")
        
        return templates.TemplateResponse("workflow_edit.html", {
            "request": request,
            "workflow": workflow,
            "step_types": [step_type.value for step_type in StepType]
        })
        
    except Exception as e:
        logger.error("编辑工作流失败", workflow_name=workflow_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/step-types")
async def get_step_types():
    """获取所有步骤类型"""
    return {"step_types": [step_type.value for step_type in StepType]}


@app.get("/api/executions/history")
async def get_execution_history(workflow_name: str = None, limit: int = 50):
    """获取执行历史"""
    try:
        history = execution_history.get_execution_history(workflow_name, limit)
        return {"history": history}
    except Exception as e:
        logger.error("获取执行历史失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/executions/{filename}")
async def get_execution_detail(filename: str):
    """获取执行详情"""
    try:
        execution_detail = execution_history.get_execution_detail(filename)
        return execution_detail
    except Exception as e:
        logger.error("获取执行详情失败", filename=filename, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# 任务优化API
@app.post("/api/tasks/optimize")
async def optimize_task(optimization_request: TaskOptimizationRequest):
    """优化任务描述"""
    try:
        logger.info("收到任务优化请求", 
                   task_length=len(optimization_request.task_description),
                   language=optimization_request.language)
        
        # 调用任务优化器
        result = await task_optimizer.optimize_task_description(
            task_description=optimization_request.task_description,
            language=optimization_request.language
        )
        
        # 构建响应
        response_data = {
            "success": result.success,
            "original_task": result.original_task,
            "optimized_task": result.optimized_task,
            "optimization_time": round(result.optimization_time, 3),
            "improvements": result.improvements
        }
        
        if not result.success:
            response_data["error_message"] = result.error_message
            logger.warning("任务优化失败", error=result.error_message)
        else:
            logger.info("任务优化成功", 
                       optimization_time=result.optimization_time,
                       improvements_count=len(result.improvements))
        
        return response_data
        
    except Exception as e:
        logger.error("任务优化接口异常", error=str(e))
        raise HTTPException(status_code=500, detail=f"任务优化失败: {str(e)}")


# 录制相关API
@app.post("/api/recording/start")
async def start_recording(recording_request: RecordingRequest, background_tasks: BackgroundTasks):
    """启动录制"""
    try:
        # 检查是否已有同名录制任务
        for task_id, task_info in recording_tasks.items():
            if task_info["name"] == recording_request.name and not task_info.get("completed", False):
                raise HTTPException(status_code=400, detail="该工作流名称已在录制中")
        
        # 生成任务ID
        task_id = f"record_{recording_request.name}_{len(recording_tasks)}"
        
        # 初始化任务描述和优化信息
        original_task = recording_request.task_description
        optimized_task = original_task
        optimization_info = None
        
        # 如果是引导式录制且开启自动优化
        if (recording_request.mode == "guided" and 
            recording_request.auto_optimize and 
            recording_request.task_description):
            
            try:
                logger.info("开始优化任务描述", task_id=task_id)
                
                # 调用任务优化器
                optimization_result = await task_optimizer.optimize_task_description(
                    task_description=recording_request.task_description,
                    language="zh"
                )
                
                if optimization_result.success:
                    optimized_task = optimization_result.optimized_task
                    optimization_info = {
                        "applied": True,
                        "original_task": optimization_result.original_task,
                        "optimized_task": optimization_result.optimized_task,
                        "optimization_time": optimization_result.optimization_time,
                        "improvements": optimization_result.improvements
                    }
                    logger.info("任务描述优化成功", 
                               task_id=task_id,
                               improvements_count=len(optimization_result.improvements))
                else:
                    # 优化失败，记录错误但继续使用原始任务
                    optimization_info = {
                        "applied": False,
                        "error_message": optimization_result.error_message
                    }
                    logger.warning("任务描述优化失败，使用原始描述", 
                                  task_id=task_id,
                                  error=optimization_result.error_message)
                    
            except Exception as e:
                # 优化过程异常，记录错误但继续使用原始任务
                optimization_info = {
                    "applied": False,
                    "error_message": f"优化过程异常: {str(e)}"
                }
                logger.warning("任务描述优化异常，使用原始描述", 
                              task_id=task_id,
                              error=str(e))
        
        # 初始化任务状态
        recording_tasks[task_id] = {
            "name": recording_request.name,
            "description": recording_request.description,
            "task_description": optimized_task,  # 使用优化后的任务描述
            "original_task": original_task,  # 保存原始任务描述
            "optimization_info": optimization_info,
            "mode": recording_request.mode,
            "headless": recording_request.headless,
            "status": "starting",
            "completed": False,
            "error": None,
            "workflow": None,
            "start_time": None
        }
        
        # 在后台启动录制任务
        if recording_request.mode == "guided":
            background_tasks.add_task(
                run_guided_recording,
                task_id,
                recording_request.name,
                optimized_task,  # 使用优化后的任务描述
                recording_request.headless,
                optimization_info  # 传递优化信息
            )
        else:
            background_tasks.add_task(
                run_interactive_recording,
                task_id,
                recording_request.name,
                recording_request.description,
                recording_request.headless
            )
        
        # 构建响应
        response = {
            "message": "录制任务已启动",
            "task_id": task_id,
            "name": recording_request.name,
            "mode": recording_request.mode
        }
        
        # 如果有优化信息，添加到响应中
        if optimization_info:
            response["optimization"] = optimization_info
        
        logger.info("录制任务已启动", task_id=task_id, name=recording_request.name, mode=recording_request.mode)
        return response
        
    except Exception as e:
        logger.error("启动录制失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recording/{task_id}/status")
async def get_recording_status(task_id: str):
    """获取录制状态"""
    try:
        if task_id not in recording_tasks:
            raise HTTPException(status_code=404, detail="录制任务不存在")
        
        task_info = recording_tasks[task_id]
        
        # 构建返回状态
        status_data = {
            "task_id": task_id,
            "name": task_info["name"],
            "description": task_info["description"],
            "mode": task_info["mode"],
            "status": task_info["status"],
            "completed": task_info["completed"],
            "start_time": task_info["start_time"],
            "error": task_info["error"]
        }
        
        # 如果录制完成，包含工作流信息
        if task_info["completed"] and task_info["workflow"]:
            workflow = task_info["workflow"]
            status_data["workflow"] = {
                "name": workflow.name,
                "description": workflow.description,
                "steps_count": len(workflow.steps),
                "file_path": f"/workflows/{workflow.name}.json"
            }
        
        return status_data
        
    except Exception as e:
        logger.error("获取录制状态失败", task_id=task_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/recording/{task_id}/stop")
async def stop_recording(task_id: str):
    """停止录制"""
    try:
        if task_id not in recording_tasks:
            raise HTTPException(status_code=404, detail="录制任务不存在")
        
        task_info = recording_tasks[task_id]
        
        if task_info["completed"]:
            return {"message": "录制已完成", "workflow_name": task_info["name"]}
        
        # 标记任务为停止状态
        task_info["status"] = "stopping"
        
        logger.info("录制停止请求已发送", task_id=task_id)
        return {"message": "录制停止请求已发送"}
        
    except Exception as e:
        logger.error("停止录制失败", task_id=task_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recording/active")
async def get_active_recordings():
    """获取活跃的录制任务"""
    try:
        active_recordings = [
            {
                "task_id": task_id,
                "name": task_info["name"],
                "status": task_info["status"],
                "mode": task_info["mode"],
                "start_time": task_info["start_time"]
            }
            for task_id, task_info in recording_tasks.items()
            if not task_info["completed"]
        ]
        
        return {"active_recordings": active_recordings}
        
    except Exception as e:
        logger.error("获取活跃录制任务失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# 录制后台任务函数
async def run_guided_recording(task_id: str, workflow_name: str, task_description: str, headless: bool, optimization_info: Optional[Dict] = None):
    """运行引导式录制后台任务"""
    import time
    
    task_info = recording_tasks[task_id]
    
    try:
        task_info["status"] = "recording"
        task_info["start_time"] = time.time()
        
        logger.info("开始引导式录制", task_id=task_id, workflow_name=workflow_name)
        
        # 创建新的录制器实例
        recording_recorder = WorkflowRecorder()
        
        # 执行引导式录制
        workflow = await recording_recorder.record_with_browser_use(
            workflow_name=workflow_name,
            task_description=task_description,
            headless=headless
        )
        
        # 如果有优化信息，更新工作流描述
        if optimization_info and optimization_info.get("applied"):
            # 将优化后的任务描述作为工作流的主要描述
            workflow.description = optimization_info["optimized_task"]
            
            # 在工作流中保存优化信息（作为元数据）
            if not hasattr(workflow, 'metadata'):
                workflow.metadata = {}
            workflow.metadata["task_optimization"] = {
                "original_task": optimization_info["original_task"],
                "optimized_task": optimization_info["optimized_task"],
                "optimization_time": optimization_info["optimization_time"],
                "improvements": optimization_info["improvements"]
            }
            
            # 重新保存工作流文件
            output_file = recording_recorder.output_dir / f"{workflow_name}.json"
            workflow.save_to_file(output_file)
            
            logger.info("工作流已更新优化后的描述", 
                       task_id=task_id, 
                       workflow_name=workflow_name)
        
        # 更新任务状态
        task_info["status"] = "completed"
        task_info["completed"] = True
        task_info["workflow"] = workflow
        
        logger.info("引导式录制完成", task_id=task_id, workflow_name=workflow_name, steps_count=len(workflow.steps))
        
    except Exception as e:
        task_info["status"] = "failed"
        task_info["completed"] = True
        task_info["error"] = str(e)
        logger.error("引导式录制失败", task_id=task_id, error=str(e))


async def run_interactive_recording(task_id: str, workflow_name: str, description: str, headless: bool):
    """运行交互式录制后台任务"""
    import time
    
    task_info = recording_tasks[task_id]
    
    try:
        task_info["status"] = "recording"
        task_info["start_time"] = time.time()
        
        logger.info("开始交互式录制", task_id=task_id, workflow_name=workflow_name)
        
        # 创建新的录制器实例
        recording_recorder = WorkflowRecorder()
        
        # 启动交互式录制
        workflow = await recording_recorder.start_recording(
            workflow_name=workflow_name,
            description=description,
            headless=headless
        )
        
        # 交互式录制需要等待用户手动停止
        # 这里我们等待停止信号或超时
        timeout = 300  # 5分钟超时
        start_time = time.time()
        
        while task_info["status"] == "recording" and (time.time() - start_time) < timeout:
            await asyncio.sleep(1)
        
        # 停止录制
        workflow = await recording_recorder.stop_recording(save=True)
        
        # 更新任务状态
        task_info["status"] = "completed"
        task_info["completed"] = True
        task_info["workflow"] = workflow
        
        logger.info("交互式录制完成", task_id=task_id, workflow_name=workflow_name)
        
    except Exception as e:
        task_info["status"] = "failed"
        task_info["completed"] = True
        task_info["error"] = str(e)
        logger.error("交互式录制失败", task_id=task_id, error=str(e))


if __name__ == "__main__":
    import uvicorn
    
    # 启动服务器
    uvicorn.run(app, host="0.0.0.0", port=8000) 