import asyncio
from typing import List, Dict
from prefect import flow, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner
from prefect.client import get_client
import json

from config.config import Config
from flows.factory.flow_config import FlowConfig
from flows.factory.single_repo_flow import safe_process_repo

@flow(
    name="batch_repo_subflow",
    task_runner=ConcurrentTaskRunner(max_workers=Config.DEFAULT_PER_BATCH_WORKERS),
    persist_result=False
)
async def batch_repo_subflow(config: FlowConfig, repos: List[Dict]):
    logger = get_run_logger()
    logger.info(f"Processing {len(repos)} repos with {Config.DEFAULT_PER_BATCH_WORKERS} workers")

    tasks = [
        safe_process_repo.submit(
            config=config,
            repo=repo,
            parent_run_id=config.parent_run_id
        )
        for repo in repos
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    success_count = sum(
        1 for r in results
        if not isinstance(r, Exception) and r.get("status") == "success"
    )

    logger.info(f"Completed {len(repos)} repos | Success: {success_count}")
    return results


async def submit_batch_subflow(config: FlowConfig, batch: List[Dict], parent_time_str: str, batch_number: int) -> str:
    logger = get_run_logger()
    try:
        async with get_client() as client:
            deployment = await client.read_deployment_by_name("batch_repo_subflow/batch_repo_subflow-deployment")
            flow_run = await client.create_flow_run_from_deployment(
                deployment_id=deployment.id,
                parameters={
                    "config": config.model_dump(),
                    "repos": [json.loads(json.dumps(r, default=str)) for r in batch]
                },
                name=f"{config.flow_prefix}_{parent_time_str}_batch_{batch_number:04d}"
            )
            return flow_run.id
    except Exception as e:
        logger.error(f"Batch submission failed: {str(e)}", exc_info=True)
        raise
