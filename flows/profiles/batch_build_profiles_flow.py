import asyncio
from prefect import flow, get_run_logger
from prefect.client import get_client
from prefect.task_runners import ConcurrentTaskRunner

PER_BATCH_WORKERS = 5   # control concurrency per batch (can adjust later)

@flow(task_runner=ConcurrentTaskRunner(max_workers=PER_BATCH_WORKERS))
async def batch_build_profiles_flow(repo_ids: list[str], batch_number: int):
    logger = get_run_logger()
    logger.info(f"Starting Batch {batch_number} with {len(repo_ids)} repos...")

    client = get_client()
    futures = []

    for repo_id in repo_ids:
        futures.append(
            asyncio.create_task(
                client.create_flow_run_from_deployment(
                    deployment_name="Batch Build Profiles",
                    parameters={"repo_id": repo_id}
                )
            )
        )

    await asyncio.gather(*futures)
    logger.info(f"Completed submitting all repos for Batch {batch_number}")