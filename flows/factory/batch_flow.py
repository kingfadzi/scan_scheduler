import asyncio
from typing import List, Dict
from prefect import flow, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner

import json
from prefect.utilities.annotations import unmapped

from config.config import Config
from flows.factory.flow_config import FlowConfig
from flows.factory.single_repo_flow import process_single_repo_flow

@flow(
    name="batch_repo_subflow",
    task_runner=ConcurrentTaskRunner(max_workers=5),
    persist_result=False
)
async def batch_repo_subflow(config: FlowConfig, repos: List[Dict], parent_run_id: str):
    logger = get_run_logger()
    logger.info(f"Starting batch_repo_subflow for {len(repos)} repositories.")
    tasks = []
    for repo in repos:
        repo_id = repo.get("repo_id", "unknown")
        logger.info(f"Submitting subflow for repo: {repo_id}")
        tasks.append(process_single_repo_flow(config, repo, parent_run_id))
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        logger.error(f"Error during execution: {e}")
        raise
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            repo_id = repos[i].get("repo_id", "unknown")
            logger.error(f"Subflow for repo {repo_id} failed: {result}")
    logger.info("Completed batch_repo_subflow")
    return results
