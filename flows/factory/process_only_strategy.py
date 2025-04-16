import asyncio
from prefect import get_run_logger
from flows.tasks.registry.task_registry import task_registry

async def process_only_repository_data(config, repo, parent_run_id):
    logger = get_run_logger()
    repo_id = repo["repo_id"]
    logger.info(f"[{repo_id}] Starting process_only strategy (DB-driven)")

    semaphore = asyncio.Semaphore(config.task_concurrency)

    async def run_task(task_name):
        async with semaphore:
            logger.info(f"[{repo_id}] Running task: {task_name}")
            task_path = task_registry.get_task_path(task_name)
            module_path, fn_name = task_path.rsplit('.', 1)
            module = __import__(module_path, fromlist=[fn_name])
            task_fn = getattr(module, fn_name)
            return await task_fn(repo=repo, run_id=parent_run_id)

    tasks = [run_task(t) for t in config.additional_tasks]
    await asyncio.gather(*tasks)

    logger.info(f"[{repo_id}] process_only strategy completed.")
    return {"status": "completed", "repo": repo_id}
