import traceback
from functools import partial
from prefect.cache_policies import NO_CACHE
from prefect import flow, task, get_run_logger
from prefect.context import get_run_context
import asyncio
from typing import Dict
from flows.factory.flow_config import FlowConfig
from tasks.base_tasks import clone_repository_task, cleanup_repo_task, update_status_task
from tasks.registry.task_registry import task_registry

METRIC_TASKS = [
    "core.lizard",
    "core.cloc",
    "core.goenry",
    "core.gitlog"
]

@task(name='Clean Up Repository Task', cache_policy=NO_CACHE)
def cleanup_hook_adapter(flow=None, flow_run=None, state=None):
    ctx = get_run_context()
    try:
        repo = ctx.flow_run.parameters["repo"]
        parent_run_id = ctx.flow_run.parameters["parent_run_id"]
        repo_dir = repo["repo_dir"]

        bound_cleanup = partial(
            cleanup_repo_task.fn,
            repo_dir=repo_dir,
            run_id=parent_run_id
        )

        return bound_cleanup()
    except KeyError as e:
        ctx.logger.error(f"Missing parameter in cleanup: {str(e)}")
    except Exception as e:
        ctx.logger.exception("Cleanup hook failed unexpectedly")


@task(name='Update Data Status Task', cache_policy=NO_CACHE)
def status_update_hook_adapter(flow=None, flow_run=None, state=None):
    ctx = get_run_context()
    try:
        repo = ctx.flow_run.parameters["repo"]
        parent_run_id = ctx.flow_run.parameters["parent_run_id"]
        repo_dir = repo["repo_dir"]

        bound_update = partial(
            update_status_task.fn,
            repo_dir=repo_dir,
            run_id=parent_run_id,
            status="completed",
            metadata={"phase": "cleanup"}
        )

        return bound_update()  # Call the underlying function directly
    except KeyError as e:
        ctx.logger.error(f"Missing parameter in status update: {str(e)}")
    except Exception as e:
        ctx.logger.exception("Status update hook failed unexpectedly")
        raise


@flow(
    name="process_single_repo_flow",
    persist_result=False,
    retries=0,
    on_completion=[cleanup_hook_adapter, status_update_hook_adapter],
    flow_run_name=lambda: get_run_context().parameters["repo"]["repo_id"]
)
async def process_single_repo_flow(config: FlowConfig, repo: Dict, parent_run_id: str):
    logger = get_run_logger()
    repo_id = repo["repo_id"]
    repo_slug = repo["repo_slug"]
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

                        result = await task_fn(repo_dir, repo, parent_run_id)
                        logger.info(f"[{repo_id}] [{task_name}] Completed")

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
        raise
        #return result

