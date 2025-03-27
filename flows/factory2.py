from tasks.base_tasks import (
    fetch_repositories_task,
    start_task,
    clone_repository_task,
    cleanup_repo_task,
    update_status_task,
    refresh_views_task
)
from prefect import flow, get_run_logger, wait
from prefect.task_runners import ConcurrentTaskRunner
from prefect.context import get_run_context
from pydantic.v2 import BaseModel, Field, ValidationError
from typing import List, Dict
import anyio

# Registry for ALL tasks (base + additional)
TASK_REGISTRY = {
    # Base tasks
    "fetch_repos": "tasks.base_tasks.fetch_repositories_task",
    "clone": "tasks.base_tasks.clone_repository_task",
    "cleanup": "tasks.base_tasks.cleanup_repo_task",
    "update_status": "tasks.base_tasks.update_status_task",
    
    # Additional build tasks
    "gradle": "tasks.java_tasks.run_gradlejdk_task",
    "maven": "tasks.java_tasks.run_mavenjdk_task",
    "go": "tasks.go_tasks.run_go_build_tool_task",
    "js": "tasks.javascript_tasks.run_javascript_build_tool_task",
    "python": "tasks.python_tasks.run_python_build_tool_task"
}

class FlowConfig(BaseModel):
    sub_dir: str = Field(..., min_length=1)
    flow_prefix: str = Field(..., regex=r'^[a-z0-9_-]+$')
    base_tasks: List[str] = Field(
        default=["clone", "update_status", "cleanup"],
        description="Core repository processing tasks"
    )
    additional_tasks: List[str] = Field(
        default=[],
        description="Extra build tasks from registry"
    )

    @property
    def all_tasks(self) -> List[str]:
        return self.base_tasks + self.additional_tasks

    def validate_tasks(self):
        valid_tasks = set(TASK_REGISTRY.keys())
        invalid = set(self.all_tasks) - valid_tasks
        if invalid:
            raise ValueError(f"Invalid tasks: {invalid}")

async def execute_task(task_name: str, repo_dir: str, repo: Dict, parent_run_id: str):
    """Execute registered tasks by name with proper imports"""
    module_path, fn_name = TASK_REGISTRY[task_name].rsplit('.', 1)
    module = __import__(module_path, fromlist=[fn_name])
    task_fn = getattr(module, fn_name)
    return await task_fn(repo_dir, repo, parent_run_id)

def create_analysis_flow(
    flow_name: str,
    default_sub_dir: str = "repos",
    default_flow_prefix: str = "analysis",
    default_batch_size: int = 100,
    work_pool_name: str = "repo-processing"
):
    @flow(name=f"{flow_name}-subflow", persist_result=True, retries=1)
    async def repo_subflow(config: FlowConfig, repo: Dict):
        logger = get_run_logger()
        ctx = get_run_context()
        repo_dir = None
        
        try:
            config.validate_tasks()
            
            async with anyio.fail_after(300):
                # Execute base tasks
                repo_dir = await clone_repository_task(
                    repo, 
                    config.sub_dir, 
                    str(ctx.flow_run.id)
                )
                
                # Execute all configured tasks
                for task_name in config.all_tasks:
                    await execute_task(task_name, repo_dir, repo, str(ctx.flow_run.id))
                
                return repo
            
        except Exception as e:
            logger.error(f"Subflow failed: {str(e)}")
            raise
        finally:
            if repo_dir:
                await cleanup_repo_task(repo_dir, str(ctx.flow_run.id))
            await update_status_task(repo, str(ctx.flow_run.id))

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
        additional_tasks: List[str] = []
    ):
        logger = get_run_logger()
        
        try:
            config = FlowConfig(
                sub_dir=sub_dir,
                flow_prefix=flow_prefix,
                additional_tasks=additional_tasks
            )
            config.validate_tasks()
            
            await start_task(flow_prefix)
            repos = await fetch_repositories_task(payload, batch_size)
            
            subflows = [
                repo_subflow(config, repo)
                for repo in repos
            ]
            
            completed = await wait(subflows)
            successful = sum(1 for r in completed if r.is_completed())
            
            return f"Processed {successful}/{len(repos)} repositories"
            
        except ValidationError as ve:
            logger.error(f"Configuration error: {str(ve)}")
            raise
        except Exception as e:
            logger.error(f"Critical failure: {str(e)}")
            raise
        finally:
            await refresh_views_task(flow_prefix)

    return main_flow
