import asyncio
from typing import List, Dict
from prefect import flow, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner

import json
from prefect.utilities.annotations import unmapped

from config.config import Config
from flows.factory.flow_config import FlowConfig
from flows.factory.single_repo_flow import process_single_repo_flow

from prefect import flow, task, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner
import asyncio


@task
async def run_subflow_async_task(config: FlowConfig, repo: dict, parent_run_id: str):
    logger = get_run_logger()
    repo_id = repo.get("repo_id", "unknown")
    logger.info(f"Starting subflow for repo: {repo_id}")
    try:
        # Wrap the async subflow call in an asyncio task
        subflow_future = asyncio.create_task(__process_single_repo_flow(config, repo, parent_run_id))
        result = await subflow_future
        logger.info(f"Completed subflow for repo: {repo_id}")
        return result
    except Exception as e:
        logger.error(f"Subflow for repo {repo_id} failed with exception: {e}")
        raise

@flow(name="batch_repo_subflow", task_runner=ConcurrentTaskRunner(max_workers=5))
async def batch_repo_subflow(config: FlowConfig, repos: list[dict], parent_run_id: str):
    logger = get_run_logger()
    logger.info(f"Starting batch_repo_subflow for {len(repos)} repositories.")
    
    # Map the async task over the repos. This returns a PrefectFutureList.
    mapped_futures = run_subflow_async_task.map(
        config=[config] * len(repos),
        repo=repos,
        parent_run_id=[parent_run_id] * len(repos)
    )
    # Convert the PrefectFutureList into a plain list of futures.
    futures_list = [future for future in mapped_futures]
    results = await asyncio.gather(*futures_list, return_exceptions=True)
    
    logger.info("Completed batch_repo_subflow")
    return results