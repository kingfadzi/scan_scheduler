import asyncio
import json
from typing import List, Dict, Optional
from prefect import flow, get_run_logger
from prefect.context import get_run_context
from prefect.task_runners import ConcurrentTaskRunner
from flows.factory.flow_config import FlowConfig
from tasks.base_tasks import fetch_repositories_task, start_task, refresh_views_task
from prefect.client import get_client


def create_analysis_flow(
        flow_name: str,
        default_sub_dir: str,
        default_flow_prefix: str,
        default_additional_tasks: Optional[List[str]] = None,
        default_batch_size: int = 100,
        processing_batch_size: int = 10,
        processing_batch_workers: int = 2,
        per_batch_workers: int = 5,
        task_concurrency: int = 3
):
    @flow(
        name=flow_name,
        description="Main analysis flow with batched processing",
        validate_parameters=False,
        task_runner=ConcurrentTaskRunner(max_workers=processing_batch_workers)
    )
    async def main_flow(
            payload: Dict,
            sub_dir: str = default_sub_dir,
            flow_prefix: str = default_flow_prefix,
            additional_tasks: List[str] = default_additional_tasks or [],
            batch_size: int = default_batch_size,
            processing_batch_size: int = processing_batch_size,
            processing_batch_workers: int = processing_batch_workers,
            per_batch_workers: int = per_batch_workers,
            task_concurrency: int = task_concurrency
    ):
        logger = get_run_logger()
        batch_futures = []
        current_batch = []
        repo_count = 0
        batch_counter = 1

        try:
            parent_run_ctx = get_run_context()
            parent_run_id = str(get_run_context().flow_run.id)
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

            logger.debug(
                "Initializing flow with config:\n"
                f"Subdir: {sub_dir}\nBatch size: {processing_batch_size}\n"
                f"Workers: {processing_batch_workers}/{per_batch_workers}\n"
                f"Additional tasks: {additional_tasks}"
            )

            await start_task(flow_prefix)

            async for repo in fetch_repositories_task(payload, batch_size):
                current_batch.append(repo)

            batch_futures.append(
                asyncio.create_task(
                    submit_batch_subflow(
                        config,
                        current_batch,
                        parent_time_str,
                        batch_counter
                    )
                )
            )

            logger.info(f"Submitted {len(batch_futures)} batches with parent time {parent_time_str}")

            if batch_futures:
                results = await asyncio.gather(*batch_futures, return_exceptions=True)
                success_count = sum(1 for res in results if not isinstance(res, Exception))
                logger.info(f"Completed {success_count}/{len(results)} batches successfully")

            return {
                "processed_repos": repo_count,
                "batches": len(batch_futures),
                "parent_run_time": parent_time_str
            }

        except Exception as e:
            logger.error(f"Main flow failed: {str(e)}", exc_info=True)
            raise
        finally:
            await refresh_views_task(flow_prefix)
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
            return flow_run.id
    except Exception as e:
        logger.error(f"Batch submission failed: {str(e)}", exc_info=True)
        raise
