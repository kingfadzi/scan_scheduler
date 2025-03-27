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
import asyncio
from asyncio import Semaphore
from asyncio import timeout
from asyncio import Queue, Semaphore
from anyio import create_task_group

# Task registry mapping names to import paths
TASK_REGISTRY = {
    "go": "tasks.go_tasks.run_go_build_tool_task",
    "js": "tasks.javascript_tasks.run_javascript_build_tool_task",
    "gradle": "tasks.java_tasks.run_gradlejdk_task",
    "maven": "tasks.java_tasks.run_mavenjdk_task",
    "python": "tasks.python_tasks.run_python_build_tool_task",

    # Additional tasks
    "ruby": "tasks.ruby_tasks.run_ruby_build_tool_task",
    "swift": "tasks.swift_tasks.run_swift_build_tool_task"
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

            async with timeout(300):
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
        task_runner=ConcurrentTaskRunner(max_workers=10),  # Not used here; we manage concurrency manually
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
            config.validate_tasks()

            await start_task(flow_prefix)
            repos = await fetch_repositories_task(payload, batch_size)

            # Create a queue for repositories
            repo_queue = Queue()
            for repo in repos:
                await repo_queue.put(repo)

            # Concurrency semaphore
            concurrency_sem = Semaphore(10)

            # Start processing with max 10 concurrent tasks
            async with create_task_group() as tg:
                async def process_repo(repo):
                    async with concurrency_sem:
                        await repo_subflow(config, repo)

                # Start initial tasks
                for _ in range(min(10, len(repos))):
                    repo = await repo_queue.get()
                    tg.start_soon(process_repo, repo)

                # Monitor task completion and add new tasks dynamically
                while not repo_queue.empty():
                    await asyncio.sleep(0.1)  # Poll for task completion
                    if tg.total_tasks() < 10:  # If there's room for more tasks
                        repo = await repo_queue.get()
                        tg.start_soon(process_repo, repo)

            return f"Processed {len(repos)} repositories"

        except Exception as e:
            logger.error(f"Critical failure: {str(e)}")
            raise
        finally:
            await refresh_views_task(flow_prefix)

    return main_flow
