import asyncio
from prefect import get_run_logger
from flows.tasks.base_tasks import clone_repository_task
from flows.tasks.registry.task_registry import task_registry

async def process_repository(config, repo, parent_run_id):
    logger = get_run_logger()
    repo_id = repo["repo_id"]
    repo_dir = await clone_repository_task(repo, config.sub_dir, parent_run_id)
    logger.info(f"[{repo_id}] Cloned repository to {repo_dir}")

    semaphore = asyncio.Semaphore(config.task_concurrency)

    async def run_task(task_name):
        async with semaphore:
            task_path = task_registry.get_task_path(task_name)
            module_path, fn_name = task_path.rsplit('.', 1)
            module = __import__(module_path, fromlist=[fn_name])
            task_fn = getattr(module, fn_name)
            return await task_fn(repo_dir, repo, parent_run_id)

    tasks = [run_task(t) for t in config.additional_tasks]
    await asyncio.gather(*tasks)

    return {"status": "completed", "repo": repo_id, "repo_dir": repo_dir}