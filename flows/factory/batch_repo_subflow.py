import asyncio
from typing import List, Dict

from asyncio import Semaphore, create_task, as_completed

from prefect import get_run_logger, flow

from flows.factory.flow_config import FlowConfig
from flows.factory.single_repo_flow import process_single_repo_flow

@flow(name="batch_repo_subflow", persist_result=False)
async def batch_repo_subflow(config: FlowConfig, repos: List[Dict], parent_run_id: str):
    logger = get_run_logger()
    logger.info(f"Processing {len(repos)} repos with parent_run_id={parent_run_id}")

    semaphore = Semaphore(config.per_batch_workers)
    tasks = []

    async def run_repo(repo):
        repo_id = repo.get("repo_id", "unknown")
        async with semaphore:
            logger.info(f"Starting repo: {repo_id}")
            try:
                result = await process_single_repo_flow(config, repo, parent_run_id)
                logger.info(f"Completed repo: {repo_id}")
                return result
            except Exception as e:
                logger.error(f"Repo {repo_id} failed: {e}")
                return e

    for repo in repos:
        tasks.append(create_task(run_repo(repo)))

    results = []
    for completed in as_completed(tasks):
        results.append(await completed)

    logger.info("Batch complete")
    return results