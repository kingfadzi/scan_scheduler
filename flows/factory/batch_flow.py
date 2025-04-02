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
    parent_run_id = config.parent_run_id

    logger.info(f"Starting batch processing of {len(repos)} repositories")

    batch_size = config.per_batch_workers
    results = []

    for batch_num, start_idx in enumerate(range(0, len(repos), batch_size), 1):
        batch = repos[start_idx:start_idx + batch_size]
        logger.info(f"Processing batch {batch_num} with {len(batch)} repos")

        # Use map with proper unmapped arguments
        batch_results = safe_process_repo.map(
            unmapped(config),
            unmapped(batch),
            unmapped(parent_run_id)
        )

        # Process results with exception handling
        processed = []
        for future in batch_results:
            try:
                result = future.result()
                processed.append(result)
            except Exception as e:
                logger.error(f"Task failed: {str(e)}")
                processed.append({"status": "error", "detail": str(e)})

        results.extend(processed)
        success = sum(1 for r in processed if r.get("status") == "success")
        logger.info(f"Batch {batch_num} complete - Success: {success}/{len(batch)}")

    overall_success = sum(1 for r in results if r.get("status") == "success")
    logger.info(f"All batches processed. Total Success: {overall_success}/{len(repos)}")
    return results





