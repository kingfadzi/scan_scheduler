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

def get_parent_flow_run():
    ctx = get_run_context()
    if hasattr(ctx, "flow_run"):
        return ctx.flow_run
    elif hasattr(ctx, "task_run") and hasattr(ctx.task_run, "parent"):
        return ctx.task_run.parent
    else:
        raise AttributeError("Flow run context is not available")

class FlowConfig(BaseModel):
    sub_dir: str = Field(..., min_length=1)
    flow_prefix: str = Field(..., pattern=r'^[a-zA-Z0-9_-]+$')
    additional_tasks: List[str] = Field(default_factory=list)
    processing_batch_workers: int = Field(2, gt=0)
    per_batch_workers: int = Field(5, gt=0)
    task_concurrency: int = Field(3, gt=0)
    parent_run_id: Optional[str] = None  # New field to hold the parent's run ID

    @validator('additional_tasks')
    def validate_tasks(cls, v):
        invalid_tasks = [t for t in v if not task_registry.validate_task(t)]
        if invalid_tasks:
            valid_tasks = "\n- ".join(task_registry.flat_map.keys())
            raise ValueError(
                f"Invalid tasks: {invalid_tasks}\nValid tasks:\n- {valid_tasks}"
            )
        return v

@flow(
    name="process_single_repo_flow",
    persist_result=True,
    retries=0,
    flow_run_name=lambda: get_run_context().parameters["repo"]["repo_id"]
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
        if not config.additional_tasks:
            logger.warning(f"[{repo_id}] No additional tasks configured")
        else:
            logger.info(f"[{repo_id}] Starting {len(config.additional_tasks)} tasks")
            task_semaphore = asyncio.Semaphore(config.task_concurrency)
            logger.debug(f"[{repo_id}] Semaphore initialized")

            async def run_task(task_name):
                try:
                    async with task_semaphore:
                        logger.info(f"[{repo_id}] [{task_name}] Starting execution")
                        task_path = task_registry.get_task_path(task_name)
                        module_path, fn_name = task_path.rsplit('.', 1)
                        module = __import__(module_path, fromlist=[fn_name])
                        task_fn = getattr(module, fn_name)
                        res = await task_fn(repo_dir, repo, parent_run_id)
                        logger.info(f"[{repo_id}] [{task_name}] Completed")
                        return res
                except Exception as e:
                    logger.error(f"[{repo_id}] [{task_name}] Failed: {str(e)}")
                    raise

            tasks = [run_task(t) for t in config.additional_tasks]
            results = await asyncio.gather(*tasks, return_exceptions=False)
            success_count = sum(1 for r in results if not isinstance(r, Exception))
            logger.info(f"[{repo_id}] Completed {success_count}/{len(tasks)} tasks")
            if success_count < len(tasks):
                raise RuntimeError(f"{len(tasks)-success_count} tasks failed")

        result["status"] = "success"
        return result

    except Exception as e:
        logger.error(f"[{repo_id}] Flow failed: {str(e)}")
        result["error"] = str(e)
        return result

    finally:
        logger.debug(f"[{repo_id}] Starting cleanup")
        try:
            await asyncio.gather(
                cleanup_repo_task(repo_dir, parent_run_id),
                update_status_task(repo, parent_run_id)
            )
        except Exception as e:
            logger.error(f"[{repo_id}] Cleanup error: {str(e)}")

@task
async def process_single_repo_task(config: FlowConfig, repo: Dict) -> Dict:
    """
    Wraps the single repository flow as a Prefect task so that its concurrency
    can be managed by the batch's ConcurrentTaskRunner.
    """
    # Use the parent_run_id from the config.
    return await process_single_repo_flow(config, repo, config.parent_run_id)

@flow(
    name="batch_repo_subflow",
    persist_result=True,
    task_runner=ConcurrentTaskRunner(max_workers=5)
)
async def batch_repo_subflow(config: FlowConfig, repos: List[Dict]):
    """
    Processes a batch of repositories.
    The parent's run ID is now included in the config.
    """
    logger = get_run_logger()
    logger.info(f"Starting batch processing of {len(repos)} repositories")

    # Launch each repository processing as a task, controlled by the batch's runner.
    results = await asyncio.gather(
        *[process_single_repo_task.submit(config, repo).result() for repo in repos],
        return_exceptions=True
    )

    success_count = sum(
        1 for r in results if not isinstance(r, Exception) and r.get("status") == "success"
    )
    logger.info(f"Batch complete - Success: {success_count}/{len(repos)}")
    return results

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
        validate_parameters=False,
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
        repo_count = 0
        batch_counter = 1
        current_batch = []

        try:
            # Get the parent flow run from the current context.
            parent_flow_run = get_parent_flow_run()
            parent_run_id = str(parent_flow_run.id)
            parent_start_time = parent_flow_run.start_time
            parent_time_str = parent_start_time.strftime("%Y%m%d_%H%M%S")

            # Create the configuration with the parent's run ID included.
            config = FlowConfig(
                sub_dir=sub_dir,
                flow_prefix=flow_prefix,
                additional_tasks=additional_tasks,
                processing_batch_workers=processing_batch_workers,
                per_batch_workers=per_batch_workers,
                task_concurrency=task_concurrency,
                parent_run_id=parent_run_id
            )

            await start_task(flow_prefix)

            async for repo in fetch_repositories_task(payload, batch_size):
                repo_count += 1
                current_batch.append(repo)
                if len(current_batch) >= processing_batch_size:
                    logger.info(f"Submitting batch {batch_counter} with {len(current_batch)} repositories")
                    # Now call the subflow without needing to pass parent_run_id separately.
                    batch_result = await batch_repo_subflow(config, current_batch.copy())
                    logger.info(f"Batch {batch_counter} result: {batch_result}")
                    current_batch = []
                    batch_counter += 1

            if current_batch:
                logger.info(f"Submitting final batch {batch_counter} with {len(current_batch)} repositories")
                batch_result = await batch_repo_subflow(config, current_batch)
                logger.info(f"Batch {batch_counter} result: {batch_result}")
                batch_counter += 1

            logger.info(f"Completed processing {repo_count} repositories in {batch_counter - 1} batches with parent time {parent_time_str}")
            return {
                "processed_repos": repo_count,
                "batches": batch_counter - 1,
                "parent_run_time": parent_time_str
            }

        except Exception as e:
            logger.error(f"Main flow failed: {str(e)}", exc_info=True)
            raise

        finally:
            await refresh_views_task(flow_prefix)
            logger.info("Main flow cleanup completed")

    return main_flow
