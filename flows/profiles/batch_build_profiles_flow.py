import asyncio

from flows.profiles.build_profile_flow import build_profile_flow
from prefect import flow, task, get_run_logger

PER_BATCH_WORKERS = 5

@flow(name="batch_repo_subflow")
async def batch_build_profiles_flow(repo_ids: list[str], batch_number: int):
    logger = get_run_logger()
    logger.info(f"Starting batch processing for {len(repo_ids)} repositories.")

    semaphore = asyncio.Semaphore(PER_BATCH_WORKERS)

    async def build_profile(repo_id: str):

        async with semaphore:
            logger.info(f"Starting subflow for repo: {repo_id}")
            try:
                result = await build_profile_flow(repo_id=repo_id)
                logger.info(f"Completed subflow for repo: {repo_id}")
                return result
            except Exception as e:
                logger.error(f"Subflow failed for {repo_id}: {str(e)}")
                return e

    tasks = [asyncio.create_task(build_profile(repo_id)) for repo_id in repo_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    logger.info("Completed batch processing")
    return results
