from tasks.base_tasks import (
    fetch_repositories_task,
    start_task,
    clone_repository_task,
    cleanup_repo_task,
    update_status_task,
    refresh_views_task
)
from prefect import flow, task, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner
from prefect.context import get_run_context
from pydantic import BaseModel, Field

from typing import List, Dict
import anyio
import asyncio

# Task registry mapping names to import paths
TASK_REGISTRY = {
    "go_build": "tasks.go_tasks.run_go_build_tool_task",
    "gradle": "tasks.java_tasks.run_gradlejdk_task",
    "maven": "tasks.java_tasks.run_mavenjdk_task",
    "javascript": "tasks.javascript_tasks.run_javascript_build_tool_task",
    "python": "tasks.python_tasks.run_python_build_tool_task"
}

class FlowConfig(BaseModel):
    sub_dir: str = Field(..., min_length=1)
    flow_prefix: str = Field(
        ..., 
        pattern=r'^[a-z0-9_-]+$',  # Changed from regex to pattern
        examples=["build-tools-2025"]
    )
    additional_tasks: List[str] = Field(
        default=[],
        description="Task names from TASK_REGISTRY"
    )

    @property
    def all_tasks(self):
        return ["clone", "update_status"] + self.additional_tasks

async def execute_task(task_name: str, repo_dir: str, repo: Dict, parent_run_id: str):
    """Dynamically execute registered tasks"""
    if task_name == "clone":
        return await clone_repository_task(repo, repo_dir, parent_run_id)
    elif task_name == "update_status":
        return await update_status_task(repo, parent_run_id)
    
    module_path, function_name = TASK_REGISTRY[task_name].rsplit('.', 1)
    module = __import__(module_path, fromlist=[function_name])
    task_fn = getattr(module, function_name)
    return await task_fn(repo_dir, repo, parent_run_id)

def create_analysis_flow(
    flow_name: str,
    default_sub_dir: str,
    default_flow_prefix: str,
    default_additional_tasks: List[str] = [],
    default_batch_size: int = 100,
    work_pool_name: str = "repo-processing"
):
    @flow(name=f"{flow_name}-subflow", persist_result=True, retries=1)
    async def repo_subflow(config: FlowConfig, repo: Dict):
        logger = get_run_logger()
        ctx = get_run_context()
        parent_run_id = str(ctx.flow_run.id)
        repo_dir = None
        
        try:
            # Validate tasks against registry
            invalid_tasks = set(config.all_tasks) - (TASK_REGISTRY.keys() | {"clone", "update_status"})
            if invalid_tasks:
                raise ValueError(f"Invalid tasks: {invalid_tasks}")
            
            async with anyio.fail_after(300):
                # Execute base tasks
                repo_dir = await clone_repository_task(repo, config.sub_dir, parent_run_id)
                
                # Execute all configured tasks
                for task_name in config.all_tasks:
                    await execute_task(task_name, repo_dir, repo, parent_run_id)
                
                return repo
            
        except Exception as e:
            logger.error(f"Subflow failed: {str(e)}")
            raise
        finally:
            if repo_dir:
                await cleanup_repo_task(repo_dir, parent_run_id)
            await update_status_task(repo, parent_run_id)

    @flow(
        name=flow_name,
        task_runner=ConcurrentTaskRunner(max_workers=10),
        validate_parameters=False
    )
    async def main_flow(
        payload: Dict,
        sub_dir: str = default_sub_dir,
        flow_prefix: str = default_flow_prefix,
        batch_size: int = default_batch_size,
        additional_tasks: List[str] = default_additional_tasks
    ):
        logger = get_run_logger()
        
        try:
            config = FlowConfig(
                sub_dir=sub_dir,
                flow_prefix=flow_prefix,
                additional_tasks=additional_tasks
            )
            
            await start_task(flow_prefix)
            repos = await fetch_repositories_task(payload, batch_size)
            
            # Create and execute all subflows
            subflows = [
                repo_subflow(config, repo)
                for repo in repos
            ]
            
            # Wait for completion with timeout
            completed = await asyncio.gather(*subflows, return_exceptions=True)
            successful = sum(1 for r in completed if not isinstance(r, Exception))
            
            logger.info(f"Completed {successful}/{len(repos)} repositories")
            return f"Processed {successful}/{len(repos)} repositories"
            
        except Exception as e:
            logger.error(f"Critical failure: {str(e)}")
            raise
        finally:
            await refresh_views_task(flow_prefix)

    return main_flow
