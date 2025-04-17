import asyncio
from datetime import datetime
from typing import Dict, List

from prefect import flow, get_run_logger
from prefect.context import get_run_context
from prefect.client import get_client
from prefect.client.schemas.filters import FlowRunFilter, DeploymentFilter

from shared.utils import Utils
from flows.factory.flow_config import FlowConfig
import json

MAX_RUNNING = 4
MAX_WAITING = 4
MAX_IN_FLIGHT = MAX_RUNNING + MAX_WAITING


@flow(name="submitter_flow")
async def submitter_flow(
    payload: Dict,
    processor_deployment: str,
    flow_prefix: str,
    batch_size: int,
    check_interval: int,
    sub_dir: str,
    additional_tasks: List[str],
    processing_batch_workers: int,
    per_batch_workers: int,
    task_concurrency: int,
):
    logger = get_run_logger()
    ctx = get_run_context()
    parent_run_id = str(ctx.flow_run.id)
    offset = 0
    batch_counter = 1

    utils = Utils(logger=logger)

    async with get_client() as client:
        deployment = await client.read_deployment_by_name(processor_deployment)
        deployment_id = deployment.id

    while True:
        async with get_client() as client:
            runs = await client.read_flow_runs(
                flow_filter=FlowRunFilter(
                    deployment=DeploymentFilter(id={"any_": [deployment_id]})
                ),
                limit=100
            )

            running = sum(
                1 for r in runs if r.state.name == "Running" and r.parameters.get("parent_run_id") == parent_run_id
            )
            waiting = sum(
                1 for r in runs if r.state.name in ("Scheduled", "Pending") and r.parameters.get("parent_run_id") == parent_run_id
            )
            in_flight = running + waiting

            logger.info(f"[{parent_run_id}] running={running}, waiting={waiting}, in_flight={in_flight}")

            if in_flight >= MAX_IN_FLIGHT:
                logger.info(f"In-flight limit ({MAX_IN_FLIGHT}) reached. Sleeping...")
                await asyncio.sleep(check_interval)
                continue

        repos = utils.fetch_repositories_batch(payload, offset=offset, batch_size=batch_size)

        if not repos:
            logger.info("No more repos. Resetting offset to 0.")
            offset = 0
            await asyncio.sleep(check_interval)
            continue

        parent_time_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        config = FlowConfig(
            sub_dir=sub_dir,
            flow_prefix=flow_prefix,
            additional_tasks=additional_tasks,
            processing_batch_workers=processing_batch_workers,
            per_batch_workers=per_batch_workers,
            task_concurrency=task_concurrency,
            parent_run_id=parent_run_id
        )

        flow_run_name = f"{flow_prefix}_{parent_time_str}_batch_{batch_counter:04d}"

        async with get_client() as client:
            await client.create_flow_run_from_deployment(
                deployment_id=deployment_id,
                parameters={
                    "config": config.model_dump(),
                    "repos": [json.loads(json.dumps(r, default=str)) for r in repos],
                    "parent_run_id": parent_run_id
                },
                name=flow_run_name
            )

        logger.info(f"Submitted batch #{batch_counter} with {len(repos)} repos")
        batch_counter += 1
        offset += batch_size
        await asyncio.sleep(check_interval)