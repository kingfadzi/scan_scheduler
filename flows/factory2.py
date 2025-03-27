import asyncio
from prefect import flow, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner
from prefect.context import get_run_context
from pydantic import BaseModel, Field
from typing import List, Dict

from tasks.base_tasks import (
    fetch_repositories_task,
    start_task,
    clone_repository_task,
    cleanup_repo_task,
    update_status_task,
    refresh_views_task
)

# Task registry including base and build tasks
TASK_REGISTRY = {
    "clone": "tasks.base_tasks.clone_repository_task",
    "cleanup": "tasks.base_tasks.cleanup_repo_task",
    "update_status": "tasks.base_tasks.update_status_task",
    "go": "tasks.go_tasks.run_go_build_tool_task",
    "js": "tasks.javascript_tasks.run_javascript_build_tool_task",
    "gradle": "tasks.java_tasks.run_gradlejdk_task",
    "maven": "tasks.java_tasks.run_mavenjdk_task",
    "python": "tasks.python_tasks.run_python_build_tool_task"
}

class FlowConfig(BaseModel):
    sub_dir: str = Field(..., min_length=1)
    flow_prefix: str = Field(..., pattern=r'^[a-zA-Z0-9_-]+$')
    additional_tasks: List[str] = Field(
        default=[],
        description=f"Available tasks: {list(TASK_REGISTRY.keys())}"
    )

    def validate_tasks(self):
        valid_tasks = set(TASK_REGISTRY.keys())
        invalid_tasks = set(self.additional_tasks) - valid_tasks
        if invalid_tasks:
            raise ValueError(f"Invalid tasks: {invalid_tasks}")

def create_analysis_flow(
        flow_name: str,
        default_sub_dir: str,
        default_flow_prefix: str,
        default_additional_tasks: List[str] = None,
        default_batch_size: int = 100,
        max_concurrent: int = 10
):
    @flow(
        name=f"{flow_name}-subflow",
        persist_result=True,
        retries=2,
        retry_delay_seconds=30
    )
    async def repo_subflow(config: FlowConfig, repo: Dict):
        logger = get_run_logger()
        ctx = get_run_context()
        parent_run_id = str(ctx.flow_run.id)
        repo_dir = None

        try:
            async with asyncio.timeout(300):
                repo_dir = await clone_repository_task(repo, config.sub_dir, parent_run_id)
                for task_name in config.additional_tasks:
                    module_path, fn_name = TASK_REGISTRY[task_name].rsplit('.', 1)
                    module = __import__(module_path, fromlist=[fn_name])
                    task_fn = getattr(module, fn_name)
                    await task_fn(repo_dir, repo, parent_run_id)
                return repo
        finally:
            if repo_dir:
                await cleanup_repo_task(repo_dir, parent_run_id)
            await update_status_task(repo, parent_run_id)

    @flow(
        name=flow_name,
        task_runner=ConcurrentTaskRunner(),
        validate_parameters=False
    )
    async def main_flow(
            payload: Dict,
            sub_dir: str = default_sub_dir,
            flow_prefix: str = default_flow_prefix,
            batch_size: int = default_batch_size,
            additional_tasks: List[str] = default_additional_tasks or []
    ):
        logger = get_run_logger()
        config = FlowConfig(
            sub_dir=sub_dir,
            flow_prefix=flow_prefix,
            additional_tasks=additional_tasks
        )
        config.validate_tasks()

        try:
            await start_task(flow_prefix)
            repos = await fetch_repositories_task(payload, batch_size)

            semaphore = asyncio.Semaphore(max_concurrent)

            async def process_repo(repo):
                async with semaphore:
                    return await repo_subflow(config, repo)

            # Create and execute all tasks with concurrency control
            tasks = [process_repo(repo) for repo in repos]
            results = await asyncio.gather(*tasks)

            successful = sum(1 for r in results if r is not None)
            return f"Processed {successful}/{len(repos)} repositories successfully"
        finally:
            await refresh_views_task(flow_prefix)

    return main_flow
