import asyncio
from typing import List, Dict
from prefect import flow, get_run_logger
from asyncio import Semaphore, create_task, as_completed

from flows.factory.flow_config import FlowConfig
from flows.factory.processing_strategy import ProcessingStrategy
from flows.factory.core_generic_flow import process_single_repo_flow
from flows.factory.strategies import get_strategy_by_name

@flow(name="batch_repo_subflow")
async def batch_repo_subflow(
    config: FlowConfig,
    repos: List[Dict],
    parent_run_id: str,
    strategy_type: str
):
    logger = get_run_logger()
    logger.info(f"Starting batch_repo_subflow for {len(repos)} repositories.")
    
    strategy = get_strategy_by_name(strategy_type)

    # Use hooks if provided
    single_repo_flow = (
        process_single_repo_flow.with_options(on_completion=strategy.on_completion_hooks)
        if strategy.on_completion_hooks else process_single_repo_flow
    )

    semaphore = Semaphore(config.per_batch_workers)
    tasks = []

    async def run_repo(repo: Dict):
        repo_id = repo.get("repo_id", "unknown")
        async with semaphore:
            logger.info(f"Starting subflow for repo: {repo_id}")
            try:
                result = await single_repo_flow(config, repo, parent_run_id, strategy)
                logger.info(f"Completed subflow for repo: {repo_id}")
                return result
            except Exception as e:
                logger.error(f"Subflow for repo {repo_id} failed with error: {e}")
                return {"status": "error", "repo": repo_id, "error": str(e)}

    for repo in repos:
        tasks.append(create_task(run_repo(repo)))

    results = [await t for t in as_completed(tasks)]
    logger.info("Completed batch_repo_subflow")
    return results