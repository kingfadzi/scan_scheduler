import asyncio
from prefect import flow
from prefect.client.orchestration import get_client
from prefect.task_runners import ConcurrentTaskRunner

from flows.tasks.base_tasks import fetch_repositories_task

MAX_PARALLEL_BATCHES = 2
REPOS_PER_BATCH = 100
DB_FETCH_BATCH_SIZE = 1000

@flow(name="main_batch_profile_orchestrator_flow", task_runner=ConcurrentTaskRunner(max_workers=MAX_PARALLEL_BATCHES))
async def main_batch_profile_orchestrator_flow(payload: dict):
    processed = 0
    current_batch = []
    batch_futures = []

    async with get_client() as client:
        deployment = await client.read_deployment_by_name(
            "batch_build_profiles_flow/batch_build_profiles_flow"
        )

        async for repo in fetch_repositories_task(payload["payload"], DB_FETCH_BATCH_SIZE):
            current_batch.append(repo)
            processed += 1

            if len(current_batch) >= REPOS_PER_BATCH:
                batch_number = (processed // REPOS_PER_BATCH)
                future = asyncio.create_task(
                    client.create_flow_run_from_deployment(
                        deployment_id=deployment.id,
                        parameters={
                            "repo_ids": [r["repo_id"] for r in current_batch],
                            "batch_number": batch_number,
                        },
                        name=f"batch-{batch_number:04d}"
                    )
                )
                batch_futures.append(future)
                current_batch = []

                if len(batch_futures) >= MAX_PARALLEL_BATCHES:
                    await asyncio.gather(*batch_futures)
                    batch_futures = []

        if current_batch:
            batch_number = (processed // REPOS_PER_BATCH) + 1
            future = asyncio.create_task(
                client.create_flow_run_from_deployment(
                    deployment_id=deployment.id,
                    parameters={
                        "repo_ids": [r["repo_id"] for r in current_batch],
                        "batch_number": batch_number,
                    },
                    name=f"batch-{batch_number:04d}"
                )
            )
            batch_futures.append(future)

        if batch_futures:
            await asyncio.gather(*batch_futures)

    print(f"Completed submitting {processed} repositories.")
