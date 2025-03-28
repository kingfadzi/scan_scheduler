import asyncio
import json
import time

from prefect import flow, get_run_logger
from prefect.context import get_run_context
from pydantic import BaseModel, Field
from typing import List, Dict
from prefect.client import get_client

from tasks.base_tasks import (
    fetch_repositories_task,
    start_task,
    clone_repository_task,
    cleanup_repo_task,
    update_status_task,
    refresh_views_task
)

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
        invalid_tasks = set(self.additional_tasks) - set(TASK_REGISTRY.keys())
        if invalid_tasks:
            raise ValueError(f"Invalid tasks: {invalid_tasks}")

@flow(
    name="batch_repo_subflow",
    persist_result=True,
    retries=0
)
async def batch_repo_subflow(config: FlowConfig, repos: List[Dict]):
    logger = get_run_logger()
    parent_run_id = str(get_run_context().flow_run.id)
    tasks = [process_single_repo(config, repo, parent_run_id) for repo in repos]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results

async def process_single_repo(config: FlowConfig, repo: Dict, parent_run_id: str):
    logger = get_run_logger()
    repo_dir = None
    result = {"status": "failed", "repo": repo.get("repo_slug", "unknown")}
    try:
        repo_dir = await clone_repository_task(repo, config.sub_dir, parent_run_id)
        for task_name in config.additional_tasks:
            module_path, fn_name = TASK_REGISTRY[task_name].rsplit('.', 1)
            module = __import__(module_path, fromlist=[fn_name])
            task_fn = getattr(module, fn_name)
            await task_fn(repo_dir, repo, parent_run_id)
        result["status"] = "success"
        return result
    except Exception as e:
        logger.error(f"Failed for repo {repo.get('repo_slug')}: {e}")
        result["error"] = str(e)
        return result
    finally:
        await asyncio.gather(
            cleanup_repo_task(repo_dir, parent_run_id),
            update_status_task(repo, parent_run_id),
            return_exceptions=True
        )

async def submit_batch_subflow(config: FlowConfig, repos: List[Dict]) -> str:
    logger = get_run_logger()
    try:
        async with get_client() as client:
            deployment = await client.read_deployment_by_name("batch_repo_subflow/batch_repo_subflow-deployment")
            flow_run = await client.create_flow_run_from_deployment(
                deployment.id,
                parameters={
                    "config": config.dict(),
                    "repos": [json.loads(json.dumps(repo, default=str)) for repo in repos]
                }
            )
        return flow_run.id
    except Exception as e:
        logger.error(f"Failed to submit batch: {str(e)}", exc_info=True)
        raise

def create_analysis_flow(
        flow_name: str,
        default_sub_dir: str,
        default_flow_prefix: str,
        default_additional_tasks: List[str] = None,
        default_batch_size: int = 100,
        processing_batch_size: int = 10
):
    @flow(name=flow_name, validate_parameters=False)
    async def main_flow(
            payload: Dict,
            sub_dir: str = default_sub_dir,
            flow_prefix: str = default_flow_prefix,
            additional_tasks: List[str] = default_additional_tasks or [],
            processing_batch_size: int = processing_batch_size
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
            futures = []
            current_batch = []
            repo_count = 0

            async for repo in fetch_repositories_task(payload, default_batch_size):
                repo_count += 1
                current_batch.append(repo)
                if len(current_batch) >= processing_batch_size:
                    futures.append(asyncio.create_task(submit_batch_subflow(config, current_batch)))
                    current_batch = []

            if current_batch:
                futures.append(asyncio.create_task(submit_batch_subflow(config, current_batch)))

            logger.info(f"Submitted {len(futures)} batches for processing")

            if futures:
                results = await asyncio.gather(*futures, return_exceptions=True)
                success_count = sum(1 for res in results if not isinstance(res, Exception))
                logger.info(f"Successfully processed {success_count}/{len(results)} batches")

            return f"Total repositories processed: {repo_count}"

        finally:
            await refresh_views_task(flow_prefix)

    return main_flow
