from tasks.base_tasks import (
    fetch_repositories_task,
    start_task,
    clone_repository_task,
    cleanup_repo_task,
    update_status_task,
    refresh_views_task
)
from prefect import flow, task, get_run_logger, timeout
from prefect.task_runners import ConcurrentTaskRunner
from prefect.context import get_run_context
from pydantic import BaseModel, Field
from typing import List, Dict
import asyncio
from asyncio import Semaphore

# Task registry mapping names to import paths
TASK_REGISTRY = {
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

    @property
    def all_tasks(self):
        return ["clone", "update_status"] + self.additional_tasks

    def validate_tasks(self):
        valid = set(TASK_REGISTRY.keys()).union({"clone", "update_status"})
        invalid = set(self.all_tasks) - valid
        if invalid:
            raise ValueError(f"Invalid tasks: {invalid}")

# Concurrency control for clone operations
clone_semaphore = Semaphore(10)

async def execute_task(task_name: str, repo_dir: str, repo: Dict, parent_run_id: str):
    """Execute registered tasks with concurrency control"""
    if task_name == "clone":
        async with clone_semaphore:
            return await clone_repository_task(repo, repo_dir, parent_run_id)
    elif task_name == "update_status":
        return await update_status_task(repo, parent_run_id)

    module_path, fn_name = TASK_REGISTRY[task_name].rsplit('.', 1)
    module = __import__(module_path, fromlist=[fn_name])
    task_fn = getattr(module, fn_name)
    return await task_fn(repo_dir, repo, parent_run_id)

def create_analysis_flow(
        flow_name: str,
        default_sub_dir: str,
        default_flow_prefix: str,
        default_additional_tasks: List[str] = [],
        default_batch_size: int = 100,
        work_pool_name: str = "fundamentals-pool"
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
            config.validate_tasks()

            async with timeout(seconds=300):
                # Process repository
                for task_name in config.all_tasks:
                    if task_name == "clone":
                        repo_dir = await execute_task(task_name, "", repo, parent_run_id)
                    else:
                        await execute_task(task_name, repo_dir, repo, parent_run_id)

                return repo

        except Exception as e:
            logger.error(f"Subflow failed: {str(e)}")
            raise
        finally:
            if repo_dir:
                await cleanup_repo_task(repo_dir, parent_run_id)

    @flow(
        name=flow_name,
        task_runner=ConcurrentTaskRunner(max_workers=10),  # 10 concurrent subflows
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
        processed = 0

        try:
            config = FlowConfig(
                sub_dir=sub_dir,
                flow_prefix=flow_prefix,
                additional_tasks=additional_tasks
            )
            config.validate_tasks()

            await start_task(flow_prefix)
            repos = await fetch_repositories_task(payload, batch_size)

            # Process in batches of 10
            for i in range(0, len(repos), 10):
                batch = repos[i:i+10]
                subflows = [repo_subflow(config, repo) for repo in batch]
                await asyncio.gather(*subflows)
                processed += len(batch)
                logger.info(f"Progress: {processed}/{len(repos)}")

            return f"Processed {len(repos)} repositories"

        except Exception as e:
            logger.error(f"Critical failure: {str(e)}")
            raise
        finally:
            await refresh_views_task(flow_prefix)

    return main_flow
