import asyncio
from typing import List, Dict
from prefect import flow, get_run_logger
from prefect.context import get_run_context
from prefect.task_runners import ConcurrentTaskRunner
from flows.factory.flow_config import FlowConfig
from tasks.base_tasks import fetch_repositories_task, start_task, refresh_views_task
from flows.factory.batch_flow import submit_batch_subflow


def create_analysis_flow(
    flow_name: str,
    default_sub_dir: str,
    default_flow_prefix: str,
    default_additional_tasks: List[str] = None,
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
            ctx = get_run_context()
            parent_run_id = str(ctx.flow_run.id)
            parent_start_time = ctx.flow_run.start_time
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

            async for repo in fetch_repositories_task(payload, batch_size):
                repo_count += 1
                current_batch.append(repo)

                if len(current_batch) >= processing_batch_size:
                    batch_futures.append(asyncio.create_task(
                        submit_batch_subflow(config, current_batch.copy(), parent_time_str, batch_counter)
                    ))
                    current_batch = []
                    batch_counter += 1

            if current_batch:
                batch_futures.append(asyncio.create_task(
                    submit_batch_subflow(config, current_batch, parent_time_str, batch_counter)
                ))

            if batch_futures:
                results = await asyncio.gather(*batch_futures, return_exceptions=True)
                success_count = sum(1 for res in results if not isinstance(res, Exception))
                logger.info(f"Completed {success_count}/{len(results)} batches successfully")

            return {
                "processed_repos": repo_count,
                "batches": len(batch_futures),
                "parent_run_time": parent_time_str
            }

        finally:
            await refresh_views_task(flow_prefix)
            logger.info("Main flow cleanup completed")

    return main_flow
