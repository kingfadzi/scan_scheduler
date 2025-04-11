import asyncio
from typing import Optional
from prefect import flow
from prefect.client.orchestration import get_client
from prefect.task_runners import ConcurrentTaskRunner

from shared.models import Session
from shared.models import Repository, RepoMetrics


MAX_PARALLEL_BATCHES = 2
REPOS_PER_BATCH = 100

def fetch_repo_chunk(last_seen_repo_id: Optional[str], limit: int, activity_status: str) -> list[str]:
    with Session() as session:
        query = (
            session.query(Repository.repo_id)
            .join(RepoMetrics, Repository.repo_id == RepoMetrics.repo_id)
            .filter(RepoMetrics.activity_status == activity_status)
            .order_by(Repository.repo_id)
        )
        if last_seen_repo_id:
            query = query.filter(Repository.repo_id > last_seen_repo_id)
        rows = query.limit(limit).all()
        return [r.repo_id for r in rows]


@flow(name="Main Batch Orchestrator", task_runner=ConcurrentTaskRunner(max_workers=MAX_PARALLEL_BATCHES))
async def main_batch_orchestrator_flow(activity_status: str = "ACTIVE"):
    processed = 0
    last_seen_repo_id = None
    batch_futures = []

    async with get_client() as client:
        deployment = await client.read_deployment_by_name(
            "batch-build-profiles-flow/batch_build_profiles_flow"
        )

        while True:

            batch_repo_ids = fetch_repo_chunk(last_seen_repo_id, REPOS_PER_BATCH, activity_status=activity_status)

            if not batch_repo_ids:
                break

            batch_number = (processed // REPOS_PER_BATCH) + 1

            future = asyncio.create_task(
                client.create_flow_run_from_deployment(
                    deployment_id=deployment.id,
                    parameters={
                        "repo_ids": batch_repo_ids,
                        "batch_number": batch_number
                    },
                    name=f"batch-{batch_number:04d}"
                )
            )
            batch_futures.append(future)

            processed += len(batch_repo_ids)
            last_seen_repo_id = batch_repo_ids[-1]

            if len(batch_futures) >= MAX_PARALLEL_BATCHES:
                await asyncio.gather(*batch_futures)
                batch_futures = []

        if batch_futures:
            await asyncio.gather(*batch_futures)

    print(f"Completed submitting {processed} repositories.")



if __name__ == "__main__":
    activity_status = "ACTIVE"
    asyncio.run(main_batch_orchestrator_flow(activity_status=activity_status))
