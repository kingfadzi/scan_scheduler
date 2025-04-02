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
    name="repo_processing_flow",
    task_runner=ConcurrentTaskRunner(max_workers=5),
    persist_result=False
)
async def repo_processing_flow(config: FlowConfig, repos: List[Dict]):
    logger = get_run_logger()
    logger.info(f"Starting processing of {len(repos)} repositories")

    # Process all repos in a single map operation
    results = await safe_process_repo.map(
        unmapped(config),
        repos,
        unmapped(config.parent_run_id)
    )

    # Handle results and exceptions
    processed = []
    for future in results:
        try:
            result = await future
            processed.append(result)
        except Exception as e:
            logger.error(f"Task failed: {str(e)}")
            processed.append({"status": "error", "detail": str(e)})

    success_count = sum(1 for r in processed if r.get("status") == "success")
    logger.info(f"Processing complete - Success: {success_count}/{len(repos)}")
    return processed






