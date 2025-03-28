# factory2.py
import asyncio
from prefect import flow, get_run_logger
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

# Task registry mapping task keys to module paths
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

# --- Dynamic Subflow ---
# This flow must be defined at module level for deployment with .submit()
@flow(
    name="repo_subflow",
    persist_result=True,
    retries=0  # Disable retries to avoid AwaitingRetry states
)
async def repo_subflow(config: FlowConfig, repo: Dict):
    """Dynamic subflow to process an individual repository."""
    logger = get_run_logger()
    parent_run_id = str(get_run_context().task_run.flow_run_id)
    repo_dir = None
    result = {"status": "failed", "repo": repo["repo_slug"]}
    try:
        # Clone repository
        repo_dir = await clone_repository_task(repo, config.sub_dir, parent_run_id)
        # Process each configured task
        for task_name in config.additional_tasks:
            module_path, fn_name = TASK_REGISTRY[task_name].rsplit('.', 1)
            module = __import__(module_path, fromlist=[fn_name])
            task_fn = getattr(module, fn_name)
            await task_fn(repo_dir, repo, parent_run_id)
        result["status"] = "success"
        return result
    except Exception as e:
        logger.error(f"Processing failed: {str(e)}")
        result["error"] = str(e)
        return result
    finally:
        # Always attempt cleanup and status update
        await asyncio.gather(
            cleanup_repo_task(repo_dir, parent_run_id),
            update_status_task(repo, parent_run_id),
            return_exceptions=True
        )

# --- Main Flow Factory ---
def create_analysis_flow(
    flow_name: str,
    default_sub_dir: str,
    default_flow_prefix: str,
    default_additional_tasks: List[str] = None,
    default_batch_size: int = 100
):
    @flow(
        name=flow_name,
        description="Main flow for continuous repository processing",
        validate_parameters=False
    )
    async def main_flow(
            payload: Dict,
            sub_dir: str = default_sub_dir,
            flow_prefix: str = default_flow_prefix,
            additional_tasks: List[str] = default_additional_tasks or []
    ):
        logger = get_run_logger()
        try:
            # Validate and initialize flow configuration
            config = FlowConfig(
                sub_dir=sub_dir,
                flow_prefix=flow_prefix,
                additional_tasks=additional_tasks
            )
            config.validate_tasks()
            await start_task(flow_prefix)
            futures = []
            # Load the deployed dynamic subflow
            from prefect.deployments import load_deployment
            deployed_repo_subflow = load_deployment("repo_subflow-deployment")
            # Stream repositories and submit each one as a dynamic subflow run
            async for repo in fetch_repositories_task(payload, default_batch_size):
                futures.append(
                    deployed_repo_subflow.submit(parameters={"config": config, "repo": repo})
                )
            # Optionally, wait for subflows to complete and log their results
            for future in futures:
                result = future.result()  # Blocks until completion
                logger.info(f"Subflow result: {result}")
            return "All repository processing jobs submitted successfully"
        finally:
            await refresh_views_task(flow_prefix)
    return main_flow