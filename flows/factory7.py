import asyncio
import json
from typing import List, Dict, Optional
from tasks.registry.task_registry import task_registry
from prefect import flow, task, get_run_logger
from prefect.context import get_run_context
from prefect.task_runners import ConcurrentTaskRunner
from pydantic import BaseModel, Field, validator
from tasks.base_tasks import (
    fetch_repositories_task,
    start_task,
    clone_repository_task,
    cleanup_repo_task,
    update_status_task,
    refresh_views_task
)

class FlowConfig(BaseModel):
    sub_dir: str = Field(..., min_length=1)
    flow_prefix: str = Field(..., pattern=r'^[a-zA-Z0-9_-]+$')
    additional_tasks: List[str] = Field(default_factory=list)
    processing_batch_workers: int = Field(2, gt=0)
    per_batch_workers: int = Field(5, gt=0)
    task_concurrency: int = Field(3, gt=0)

    @validator('additional_tasks')
    def validate_tasks(cls, v):
        invalid_tasks = [t for t in v if not task_registry.validate_task(t)]
        if invalid_tasks:
            valid_tasks = "\n- ".join(task_registry.flat_map.keys())
            raise ValueError(f"Invalid tasks: {invalid_tasks}\nValid tasks:\n- {valid_tasks}")
        return v

@flow(
    name="process_single_repo_flow",
    persist_result=True,
    retries=0,
    flow_run_name=lambda: get_run_context().parameters["repo"]["repo_id"],
    task_runner=ConcurrentTaskRunner(max_workers=3)  # Task-level concurrency
)
async def process_single_repo_flow(config: FlowConfig, repo: Dict, parent_run_id: str):
    logger = get_run_logger()
    repo_id = repo["repo_id"]
    repo_dir = None
    result = {"status": "failed", "repo": repo_id}

    try:
        # --- Cloning Phase ---
        logger.debug(f"[{repo_id}] Starting cloning process")
        repo_dir = await clone_repository_task(repo, config.sub_dir, parent_run_id)
        logger.info(f"[{repo_id}] Successfully cloned to {repo_dir}")

        # --- Additional Tasks Execution ---
        if config.additional_tasks:
            task_futures = [
                execute_additional_task.submit(
                    repo_dir,
                    repo,
                    parent_run_id,
                    task_name,
                    config.task_concurrency
                )
                for task_name in config.additional_tasks
            ]

            task_results = await asyncio.gather(*task_futures, return_exceptions=True)
            success_count = sum(1 for r in task_results if not isinstance(r, Exception))

            logger.info(f"[{repo_id}] Completed {success_count}/{len(task_results)} tasks")
            if success_count < len(task_results):
                raise RuntimeError(f"{len(task_results)-success_count} tasks failed")

        result["status"] = "success"
        return result

    except Exception as e:
        logger.error(f"[{repo_id}] Flow failed: {str(e)}")
        result["error"] = str(e)
        return result
    finally:
        logger.debug(f"[{repo_id}] Starting cleanup")
        await asyncio.gather(
            cleanup_repo_task.submit(repo_dir, parent_run_id),
            update_status_task.submit(repo, parent_run_id),
            return_exceptions=True
        )

@task
async def execute_additional_task(repo_dir, repo, parent_id, task_name, concurrency):
    logger = get_run_logger()
    repo_id = repo["repo_id"]

    try:
        task_semaphore = asyncio.Semaphore(concurrency)
        async with task_semaphore:
            logger.info(f"[{repo_id}] [{task_name}] Starting execution")

            task_path = task_registry.get_task_path(task_name)
            module_path, fn_name = task_path.rsplit('.', 1)
            module = __import__(module_path, fromlist=[fn_name])
            task_fn = getattr(module, fn_name)

            result = await task_fn(repo_dir, repo, parent_id)
            logger.info(f"[{repo_id}] [{task_name}] Completed")
            return result

    except Exception as e:
        logger.error(f"[{repo_id}] [{task_name}] Failed: {str(e)}")
        raise

@flow(
    name="batch_repo_subflow",
    task_runner=ConcurrentTaskRunner(max_workers=5),
    persist_result=True
)
async def batch_repo_subflow(config: FlowConfig, repos: List[Dict], parent_run_id: str, batch_number: int):
    logger = get_run_logger()
    logger.info(f"Starting batch {batch_number} with {len(repos)} repositories")

    results = await asyncio.gather(
        *[process_single_repo_flow(config, repo, parent_run_id) for repo in repos],
        return_exceptions=True
    )

    success_count = sum(1 for r in results if not isinstance(r, Exception) and r.get("status") == "success")
    logger.info(f"Batch {batch_number} complete - Success: {success_count}/{len(repos)}")
    return results

@task(name="process_batch_task")
async def process_batch_task(config: FlowConfig, batch: List[Dict], batch_number: int, parent_run_id: str):
    """Task wrapper for batch processing"""
    return await batch_repo_subflow(config, batch, parent_run_id, batch_number)

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
        description="Main analysis flow with batched processing",
        task_runner=ConcurrentTaskRunner(max_workers=processing_batch_workers)
    )
    async def main_flow(payload: Dict):
        logger = get_run_logger()
        repo_count = 0
        batch_counter = 1
        current_batch = []
        batch_futures = []

        try:
            parent_run_ctx = get_run_context()
            parent_run_id = str(parent_run_ctx.flow_run.id)
            parent_time_str = parent_run_ctx.flow_run.start_time.strftime("%Y%m%d_%H%M%S")

            config = FlowConfig(
                sub_dir=default_sub_dir,
                flow_prefix=default_flow_prefix,
                additional_tasks=default_additional_tasks or [],
                processing_batch_workers=processing_batch_workers,
                per_batch_workers=per_batch_workers,
                task_concurrency=task_concurrency
            )

            await start_task(flow_prefix=default_flow_prefix)

            # Stream and batch repositories
            async for repo in fetch_repositories_task.submit(payload, default_batch_size):
                repo_count += 1
                current_batch.append(repo)

                if len(current_batch) >= processing_batch_size:
                    batch_futures.append(
                        process_batch_task.submit(
                            config,
                            current_batch.copy(),
                            batch_counter,
                            parent_run_id
                        )
                    )
                    current_batch = []
                    batch_counter += 1

            # Submit final batch
            if current_batch:
                batch_futures.append(
                    process_batch_task.submit(
                        config,
                        current_batch,
                        batch_counter,
                        parent_run_id
                    )
                )

            # Process results
            total_success = 0
            if batch_futures:
                batch_results = await asyncio.gather(*batch_futures, return_exceptions=True)
                for result in batch_results:
                    if not isinstance(result, Exception):
                        total_success += sum(1 for r in result if isinstance(r, dict) and r.get("status") == "success")

            logger.info(f"Total processed: {repo_count} | Successful: {total_success}")
            return {
                "processed_repos": repo_count,
                "success_count": total_success,
                "parent_run_time": parent_time_str
            }

        except Exception as e:
            logger.error(f"Main flow failed: {str(e)}", exc_info=True)
            raise
        finally:
            await refresh_views_task(flow_prefix=default_flow_prefix)
            logger.info("Main flow cleanup completed")

    return main_flow
