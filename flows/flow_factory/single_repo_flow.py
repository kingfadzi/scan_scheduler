from prefect import flow, task, get_run_logger, get_run_context
import asyncio
from typing import Dict
from config import FlowConfig
from tasks.base_tasks import clone_repository_task, cleanup_repo_task, update_status_task
from tasks.registry.task_registry import task_registry

METRIC_TASKS = [
    "core.lizard",
    "core.cloc",
    "core.goenry",
    "core.gitlog"
]

@flow(
    name="process_single_repo_flow",
    persist_result=False,
    retries=0,
    flow_run_name=lambda: get_run_context().parameters["repo"]["repo_id"]
)
async def process_single_repo_flow(config: FlowConfig, repo: Dict, parent_run_id: str):
    logger = get_run_logger()
    repo_id = repo["repo_id"]
    repo_dir = None
    result = {"status": "failed", "repo": repo_id}

    try:
        logger.debug(f"[{repo_id}] Starting cloning process")
        repo_dir = await clone_repository_task(repo, config.sub_dir, parent_run_id)
        logger.info(f"[{repo_id}] Successfully cloned to {repo_dir}")

        if config.additional_tasks:
            logger.info(f"[{repo_id}] Starting {len(config.additional_tasks)} additional tasks")
            sem = asyncio.Semaphore(config.task_concurrency)

            async def run_task(task_name):
                async with sem:
                    try:
                        logger.info(f"[{repo_id}] [{task_name}] Starting execution")
                        task_path = task_registry.get_task_path(task_name)
                        module_path, fn_name = task_path.rsplit('.', 1)
                        module = __import__(module_path, fromlist=[fn_name])
                        task_fn = getattr(module, fn_name)
                        future = task_fn.submit(repo_dir, repo, parent_run_id)
                        result = await future.result()
                        logger.info(f"[{repo_id}] [{task_name}] Completed")
                        return result
                    except Exception as e:
                        logger.error(f"[{repo_id}] [{task_name}] Failed: {str(e)}")
                        raise

            priority_tasks = []
            other_tasks = []
            for task_name in config.additional_tasks:
                if task_name in METRIC_TASKS:
                    priority_tasks.append(task_name)
                else:
                    other_tasks.append(task_name)

            # Run priority metric tasks first (any order)
            await asyncio.gather(*(run_task(t) for t in priority_tasks))
            # Then run remaining tasks (any order)
            await asyncio.gather(*(run_task(t) for t in other_tasks))

        else:
            logger.warning(f"[{repo_id}] No additional tasks configured")

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

@task(task_run_name="{repo[repo_slug]}", retries=1)
async def safe_process_repo(config: FlowConfig, repo: Dict, parent_run_id: str):
    try:
        result = await process_single_repo_flow(config, repo, parent_run_id)
        return {"status": "success", **result}
    except Exception as e:
        return {"status": "error", "exception": str(e), "repo": repo['repo_id']}
