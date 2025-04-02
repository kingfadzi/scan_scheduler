import asyncio
from typing import List, Dict
from prefect import flow, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner

import json
from prefect.utilities.annotations import unmapped

from config.config import Config
from flows.factory.flow_config import FlowConfig
from flows.factory.single_repo_flow import safe_process_repo

@flow(
    name="batch_repo_subflow",
    task_runner=ConcurrentTaskRunner(max_workers=5),
    persist_result=False
)
async def batch_repo_subflow(config: FlowConfig, repos: List[Dict]):
    logger = get_run_logger()
    logger.info(f"Starting processing of {len(repos)} repositories")

    batch_results = safe_process_repo.map(
        unmapped(config),
        repos,
        unmapped(config.parent_run_id)
    )

    results = []
    for future in batch_results:
        try:
            result = future.result()
            results.append(result)
        except Exception as e:
            results.append({"status": "error", "detail": str(e)})

    return results



