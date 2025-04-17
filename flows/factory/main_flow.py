import asyncio
import json
from typing import List, Dict, Optional
from prefect import flow, get_run_logger
from prefect.context import get_run_context
from prefect.task_runners import ConcurrentTaskRunner
from flows.factory.flow_config import FlowConfig
from flows.tasks.base_tasks import fetch_repositories_task, start_task
from prefect.client import get_client
from prefect.client.schemas.sorting import FlowRunSort


async def get_active_flow_run_count(client, deployment_id):
    flow_runs = await client.read_flow_runs(
        deployment_id=deployment_id,
        limit=20,
        sort=[FlowRunSort.CREATED_DESC]
    )
    return sum(1 for run in flow_runs if run.state.name in {"RUNNING", "SCHEDULED", "PENDING"})


def create_analysis_flow(
        flow_name: str,
        default_sub_dir: str,
        default_flow_prefix: str,
        default_additional_tasks: Optional[List[str]],
        default_db_fetch_batch_size: int,
        default_processing_batch_size: int,
        default_processing_batch_workers: int,
        default_per_batch_workers: int,
        default_task_concurrency: int
):
    @flow(
        name=flow_name,
        description="Main analysis flow with batched processing",
        validate_parameters=False,
        task_runner=ConcurrentTaskRunner(max_workers=default_processing_batch_workers)
    )
    async def main_flow(
            payload: Dict,
            sub_dir: str = default_sub_dir,
            flow_prefix: str = default_flow_prefix,
            additional_tasks: List[str] = default_additional_tasks or [],
            db_fetch_batch_size: int = default_db_fetch_batch_size,
            processing_batch_size: int = default_processing_batch_size,
            processing_batch_workers: int = default_processing_batch_workers,
            per_batch_workers: int = default_per_batch_workers,
            task_concurrency: int = default_task_concurrency
    ):
        logger = get_run_logger()
        repo_count = 0
        current_batch = []
        batch_counter = 1
        MAX_ACTIVE_BATCHES = 8

        try:
            parent_run_ctx = get_run_context()
            parent_run_id = str(parent_run_ctx.flow_run.id)
            parent_start_time = parent_run_ctx.flow_run.start_time
            parent_time_str = parent_start_time.strftime("%Y%m%d_%H%M%S")

            config = FlowConfig(
                sub_dir=sub_dir,
                flow_prefix=flow_prefix,
                additional_tasks=additional_tasks,
                processing_batch_workers=processing_batch_workers,
                per_batch_workers=per_batch_workers,
                task_concurrency=task_concurrency,
                parent_run_id=parent_run_id
            )

            await start_task(flow_prefix)

            async with get_client() as client:
                deployment = await client.read_deployment_by_name(
                    "main_analysis_flow/main-analysis-deployment"
                )

                async for repo in fetch_repositories_task(payload, db_fetch_batch_size):
                    repo_count += 1
                    current_batch.append(repo)

                    if len(current_batch) >= processing_batch_size:
                        while True:
                            active_count = await get_active_flow_run_count(client, deployment.id)
                            if active_count < MAX_ACTIVE_BATCHES:
                                break
                            logger.debug(f"{active_count} active batches — waiting to drop below {MAX_ACTIVE_BATCHES}...")
                            await asyncio.sleep(10)

                        logger.info(f"Submitting batch {batch_counter:04d}")
                        await submit_batch_subflow(
                            config, current_batch.copy(), parent_time_str, batch_counter
                        )
                        current_batch = []
                        batch_counter += 1

                if current_batch:
                    while True:
                        active_count = await get_active_flow_run_count(client, deployment.id)
                        if active_count < MAX_ACTIVE_BATCHES:
                            break
                        logger.debug(f"{active_count} active batches — waiting to drop below {MAX_ACTIVE_BATCHES}...")
                        await asyncio.sleep(10)

                    logger.info(f"Submitting final batch {batch_counter:04d}")
                    await submit_batch_subflow(
                        config, current_batch, parent_time_str, batch_counter
                    )
                    batch_counter += 1

                logger.info(f"Submitted {batch_counter - 1} batches for {repo_count} repositories.")

                # Self-trigger next run
                logger.info("Triggering next run of this flow...")
                await client.create_flow_run_from_deployment(
                    deployment_id=deployment.id,
                    parameters={"payload": payload},
                    name=f"auto_rerun_after_{parent_time_str}"
                )

            return {
                "processed_repos": repo_count,
                "batches": batch_counter - 1,
                "parent_run_time": parent_time_str
            }

        except Exception as e:
            logger.error(f"Main flow failed: {str(e)}", exc_info=True)
            raise
        finally:
            logger.info("Main flow cleanup completed")

    return main_flow


async def submit_batch_subflow(
        config: FlowConfig,
        batch: List[Dict],
        parent_start_time: str,
        batch_number: int
) -> str:
    logger = get_run_logger()
    try:
        async with get_client() as client:
            deployment = await client.read_deployment_by_name(
                "batch_repo_subflow/batch_repo_subflow-deployment"
            )

            flow_run_name = (f"{config.flow_prefix}_"
                             f"{parent_start_time}_batch_{batch_number:04d}")

            flow_run = await client.create_flow_run_from_deployment(
                deployment_id=deployment.id,
                parameters={
                    "config": config.model_dump(),
                    "parent_run_id": config.parent_run_id,
                    "repos": [json.loads(json.dumps(r, default=str)) for r in batch]
                },
                name=flow_run_name
            )
            logger.info(f"Submitted {flow_run_name} (ID: {flow_run.id})")
            return flow_run.id
    except Exception as e:
        logger.error(f"Batch submission failed: {str(e)}", exc_info=True)
        raise