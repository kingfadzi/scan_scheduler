import asyncio
from datetime import datetime
from typing import Dict, List

from prefect import flow, get_run_logger
from prefect.context import get_run_context
from prefect.client import get_client
from prefect.client.schemas.filters import FlowRunFilter
from prefect.client.schemas.sorting import FlowRunSort
from prefect.runtime import flow_run
from shared.utils import Utils
from flows.factory.flow_config import FlowConfig
import json
import traceback

MAX_RUNNING = 4
MAX_WAITING = 4
MAX_IN_FLIGHT = MAX_RUNNING + MAX_WAITING
RETRY_DELAY_SECONDS = 10

def generate_submitter_flow_name():
    flow_prefix = flow_run.parameters.get("flow_prefix", "UNNAMED_FLOW")
    return f"{flow_prefix}_SUBMITTER_FLOW"

@flow(
    name="submitter_flow",
    flow_run_name=generate_submitter_flow_name,
    persist_result=False
)
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

    logger.info(
        f"Starting submitter flow - "
        f"Processor: {processor_deployment}, "
        f"Batch size: {batch_size}, "
        f"Max in-flight: {MAX_IN_FLIGHT} ({MAX_RUNNING} running + {MAX_WAITING} waiting), "
        f"Check interval: {check_interval}s, "
        f"Workers: {processing_batch_workers}"
    )

    parent_time_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    try:
        async with get_client() as client:
            deployment = await client.read_deployment_by_name(processor_deployment)
            deployment_id = deployment.id
            logger.debug(f"Resolved deployment '{processor_deployment}' to ID: {deployment_id}")
    except Exception as e:
        logger.error(f"Failed to fetch deployment '{processor_deployment}': {str(e)}")
        logger.debug(traceback.format_exc())
        return


    while True:
        try:
            logger.debug(f"Processing cycle started - Batch: {batch_counter}, Offset: {offset}")

            async with get_client() as client:
                runs = await client.read_flow_runs(
                    flow_run_filter=FlowRunFilter(
                        deployment_id={"any_": [deployment_id]},
                        tags={"any_": [f"parent_run_id={parent_run_id}"]}
                    ),
                    sort=FlowRunSort.START_TIME_DESC
                )

                running = sum(1 for r in runs if r.state.name == "Running")
                waiting = sum(1 for r in runs if r.state.name in ("Scheduled", "Pending", "Late"))
                in_flight = running + waiting

                logger.info(
                    f"Queue status - "
                    f"Running: {running}/{MAX_RUNNING}, "
                    f"Waiting: {waiting}/{MAX_WAITING}, "
                    f"Total in-flight: {in_flight}/{MAX_IN_FLIGHT}, "
                    f"Batches submitted: {batch_counter-1}, "
                    f"Estimated repos: {(batch_counter-1)*batch_size}"
                )

                if in_flight >= MAX_IN_FLIGHT:
                    logger.warning(
                        f"Throttling active - in-flight limit reached ({in_flight}/{MAX_IN_FLIGHT}), "
                        f"Next check in {check_interval}s"
                    )
                    await asyncio.sleep(check_interval)
                    continue

            repos = utils.fetch_repositories_batch(payload=payload, offset=offset, batch_size=batch_size)
            logger.debug(f"Fetched {len(repos)} repos (offset: {offset}, batch size: {batch_size})")

            if not repos:
                logger.info(
                    f"No repositories found at offset {offset}, "
                    f"Resetting to offset 0, "
                    f"Total processed: {batch_counter-1} batches ({(batch_counter-1)*batch_size} repos)"
                )
                offset = 0
                parent_time_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                await asyncio.sleep(check_interval)
                continue


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

            logger.info(
                f"Submitting batch #{batch_counter} - "
                f"Repos: {len(repos)}, "
                f"Flow name: {flow_run_name}, "
                f"Current offset: {offset}, "
                f"Next offset: {offset + batch_size}"
            )

            async with get_client() as client:
                flow_run = await client.create_flow_run_from_deployment(
                    deployment_id=deployment_id,
                    parameters={
                        "config": config.model_dump(),
                        "repos": [json.loads(json.dumps(r, default=str)) for r in repos],
                        "parent_run_id": parent_run_id
                    },
                    name=flow_run_name,
                    tags=[f"parent_run_id={parent_run_id}"]
                )
                logger.debug(f"Created flow run: {flow_run.name} (ID: {flow_run.id})")

            batch_counter += 1
            offset += batch_size
            await asyncio.sleep(check_interval)

        except Exception as e:
            logger.error(
                f"Error in batch #{batch_counter} (offset: {offset}): {str(e)}, "
                f"Retrying in {RETRY_DELAY_SECONDS}s"
            )
            logger.debug(traceback.format_exc())
            await asyncio.sleep(RETRY_DELAY_SECONDS)
