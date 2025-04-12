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

from asyncio import Semaphore, create_task, as_completed

@flow(name="batch_repo_subflow")
async def batch_repo_subflow(config: FlowConfig, repos: list[dict], parent_run_id: str):
    logger = get_run_logger()
    logger.info(f"Starting batch_repo_subflow for {len(repos)} repositories.")

    semaphore = Semaphore(config.per_batch_workers)
    tasks = []

    async def run_repo(repo):
        repo_id = repo.get("repo_id", "unknown")
        async with semaphore:
            logger.info(f"Starting subflow for repo: {repo_id}")
            try:
                result = await process_single_repo_flow(config, repo, parent_run_id)
                logger.info(f"Completed subflow for repo: {repo_id}")
                return result
            except Exception as e:
                logger.error(f"Subflow for repo {repo_id} failed with error: {e}")
                return e

    for repo in repos:
        task = create_task(run_repo(repo))
        tasks.append(task)

    results = []
    for completed_task in as_completed(tasks):
        result = await completed_task
        results.append(result)

    logger.info("Completed batch_repo_subflow")
    return results
