import asyncio

from prefect import task, get_run_logger
from prefect.cache_policies import NO_CACHE
from plugins.core.cloning import CloningAnalyzer
from shared.utils import Utils


@task(name="Fetch Repositories Task")
async def fetch_repositories_task(payload: dict, batch_size):
    logger = get_run_logger()
    utils = Utils(logger=logger)

    async for batch in utils.fetch_repositories_dict_async(payload, batch_size):
        for repo in batch:
            yield repo
        await asyncio.sleep(0)  # Yield control after each batch


@task(name="Start Task")
async def start_task(flow_prefix: str) -> str:
    logger = get_run_logger()
    logger.info(f"[{flow_prefix}] Starting flow")
    return flow_prefix


@task(name="Clone Repository Task", cache_policy=NO_CACHE)
async def clone_repository_task(repo, sub_dir, run_id):
    logger = get_run_logger()
    cloning_analyzer = CloningAnalyzer(logger=logger, run_id=run_id)
    result = cloning_analyzer.clone_repository(repo=repo, sub_dir=sub_dir)
    return result


@task(name="Clean Up Repository Task", cache_policy=NO_CACHE)
async def cleanup_repo_task(repo_dir, run_id):
    logger = get_run_logger()
    cloning_analyzer = CloningAnalyzer(logger=logger, run_id=run_id)
    cloning_analyzer.cleanup_repository_directory(repo_dir)


@task(name="Update Processing Status Task", cache_policy=NO_CACHE)
async def update_status_task(repo, run_id):
    logger = get_run_logger()
    utils = Utils(logger=logger)
    utils.determine_final_status(repo=repo, run_id=run_id)


@task(name="Refresh Views Task")
async def refresh_views_task(flow_prefix: str) -> None:
    logger = get_run_logger()
    logger.info(f"[{flow_prefix}] Refreshing views")
    utils = Utils(logger = get_run_logger())
    utils.refresh_views()
    logger.info(f"[{flow_prefix}] Views refreshed")
