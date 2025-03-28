import asyncio
import json
from typing import List, Dict, Optional

from prefect import flow, task, get_run_logger
from prefect.context import get_run_context
from prefect.task_runners import ConcurrentTaskRunner
from prefect.client import get_client
from pydantic import BaseModel, Field, validator

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
    additional_tasks: List[str] = Field(default_factory=list)
    processing_batch_workers: int = Field(2, gt=0)
    per_batch_workers: int = Field(5, gt=0)
    task_concurrency: int = Field(3, gt=0)

    @validator('additional_tasks')
    def validate_tasks(cls, v):
        invalid_tasks = set(v) - set(TASK_REGISTRY.keys())
        if invalid_tasks:
            raise ValueError(f"Invalid tasks: {invalid_tasks}")
        return v

@flow(
    name="process_single_repo_flow",
    persist_result=True,
    retries=0
)
async def process_single_repo_flow(config: FlowConfig, repo: Dict, parent_run_id: str):
    logger = get_run_logger()
    repo_slug = repo.get("repo_slug", "unknown")
    repo_dir = None
    result = {"status": "failed", "repo": repo_slug}

    try:
        repo_dir = await clone_repository_task(repo, config.sub_dir, parent_run_id)

        task_semaphore = asyncio.Semaphore(config.task_concurrency)

        async def run_task(task_name):
            async with task_semaphore:
                module_path, fn_name = TASK_REGISTRY[task_name].rsplit('.', 1)
                module = __import__(module_path, fromlist=[fn_name])
                task_fn = getattr(module, fn_name)
                return await task_fn(repo_dir, repo, parent_run_id)

        await asyncio.gather(*[run_task(t) for t in config.additional_tasks])

        result["status"] = "success"
        return result
    except Exception as e:
        logger.error(f"Failed processing {repo_slug}: {str(e)}")
        result["error"] = str(e)
        return result
    finally:
        await asyncio.gather(
            cleanup_repo_task(repo_dir, parent_run_id),
            update_status_task(repo, parent_run_id),
            return_exceptions=True
        )

@flow(
    name="batch_repo_subflow",
    task_runner=ConcurrentTaskRunner(max_workers=5),
    persist_result=True
)
async def batch_repo_subflow(config: FlowConfig, repos: List[Dict]):
    logger = get_run_logger()
    parent_run_id = str(get_run_context().flow_run.id)
    logger.info(f"Starting batch processing of {len(repos)} repositories")

    results = await asyncio.gather(
        *[process_single_repo_flow(config, repo, parent_run_id) for repo in repos],
        return_exceptions=True
    )

    success_count = sum(1 for r in results if not isinstance(r, Exception) and r.get("status") == "success")
    logger.info(f"Batch complete - Success: {success_count}/{len(repos)}")
    return results


async def submit_batch_subflow(config: FlowConfig, batch: List[Dict]) -> str:
    """Submit a batch of repositories for processing"""
    logger = get_run_logger()
    try:
        async with get_client() as client:
            # Get the deployment for batch processing
            deployment = await client.read_deployment_by_name(
                "batch_repo_subflow/batch_repo_subflow-deployment"
            )

            # Create a flow run for this batch
            flow_run = await client.create_flow_run_from_deployment(
                deployment.id,
                parameters={
                    "config": config.dict(),
                    "repos": [json.loads(json.dumps(r, default=str)) for r in batch]
                }
            )
            return flow_run.id
    except Exception as e:
        logger.error(f"Batch submission failed: {str(e)}", exc_info=True)
        raise

def create_analysis_flow(
        flow_name: str,
        default_sub_dir: str,
        default_flow_prefix: str,
        default_additional_tasks: Optional[List[str]] = None,
        default_batch_size: int = 100,
        processing_batch_size: int = 10,
        processing_batch_workers: int = 2,
        per_batch_workers: int = 5,
        task_concurrency: int = 3
):
    @flow(
        name=flow_name,
        description="Main analysis flow with concurrency controls",
        validate_parameters=False,
        task_runner=ConcurrentTaskRunner(max_workers=processing_batch_workers),
        work_pool_name="batch-pool"
    )
    async def main_flow(
            payload: Dict,
            sub_dir: str = default_sub_dir,
            flow_prefix: str = default_flow_prefix,
            additional_tasks: List[str] = default_additional_tasks or [],
            batch_size: int = default_batch_size,
            processing_batch_size: int = processing_batch_size,
            processing_batch_workers: int = processing_batch_workers,
            per_batch_workers: int = per_batch_workers,
            task_concurrency: int = task_concurrency
    ):
        logger = get_run_logger()
        batch_futures = []
        current_batch = []
        repo_count = 0

        try:
            config = FlowConfig(
                sub_dir=sub_dir,
                flow_prefix=flow_prefix,
                additional_tasks=additional_tasks,
                processing_batch_workers=processing_batch_workers,
                per_batch_workers=per_batch_workers,
                task_concurrency=task_concurrency
            )

            await start_task(flow_prefix)

            async for repo in fetch_repositories_task(payload, batch_size):
                repo_count += 1
                current_batch.append(repo)

                if len(current_batch) >= processing_batch_size:
                    batch_futures.append(
                        asyncio.create_task(
                            submit_batch_subflow(config, current_batch.copy())
                        )
                    )
                    current_batch = []

            if current_batch:
                batch_futures.append(
                    asyncio.create_task(submit_batch_subflow(config, current_batch))
                )

            logger.info(f"Submitted {len(batch_futures)} batches containing {repo_count} repositories")

            if batch_futures:
                results = await asyncio.gather(*batch_futures, return_exceptions=True)
                success_count = sum(1 for res in results if not isinstance(res, Exception))
                logger.info(f"Completed {success_count}/{len(results)} batches successfully")

            return {"processed_repos": repo_count, "batches": len(batch_futures)}

        except Exception as e:
            logger.error(f"Flow failed: {str(e)}", exc_info=True)
            raise
        finally:
            await refresh_views_task(flow_prefix)
            logger.info("Cleanup completed")

    return main_flow
