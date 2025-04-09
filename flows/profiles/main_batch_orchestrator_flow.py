import asyncio
from typing import Optional
from prefect import flow
from prefect.client import get_client
from prefect.task_runners import ConcurrentTaskRunner

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.models import Repository

# --- DB Setup
DATABASE_URL = "postgresql://postgres:postgres@192.168.1.188:5432/gitlab-usage"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# --- Parameters
MAX_PARALLEL_BATCHES = 2      # How many batches running at once
REPOS_PER_BATCH = 100         # How many repos per batch

# --- DB Helper: Fetch next chunk of repo IDs
def fetch_repo_chunk(last_seen_repo_id: Optional[str], limit: int) -> list[str]:
    with SessionLocal() as session:
        query = session.query(Repository.repo_id).order_by(Repository.repo_id)
        if last_seen_repo_id:
            query = query.filter(Repository.repo_id > last_seen_repo_id)
        rows = query.limit(limit).all()
        return [r.repo_id for r in rows]

# --- Main Batch Orchestrator
@flow(name="Main Batch Orchestrator", task_runner=ConcurrentTaskRunner(max_workers=MAX_PARALLEL_BATCHES))
async def main_batch_orchestrator_flow():
    processed = 0
    last_seen_repo_id = None
    batch_futures = []

    async with get_client() as client:

        deployment = await client.read_deployment_by_name(
            "batch-build-profiles-flow/batch_build_profiles_flow"
        )

        while True:
            batch_repo_ids = fetch_repo_chunk(last_seen_repo_id, REPOS_PER_BATCH)

            if not batch_repo_ids:
                break  # No more repos to process

            batch_number = (processed // REPOS_PER_BATCH) + 1

            # Launch batch deployment
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

            # Control how many batches in flight
            if len(batch_futures) >= MAX_PARALLEL_BATCHES:
                await asyncio.gather(*batch_futures)
                batch_futures = []

        # Gather any remaining batches
        if batch_futures:
            await asyncio.gather(*batch_futures)

    print(f"Completed submitting {processed} repositories.")

# --- Script Launcher
if __name__ == "__main__":
    asyncio.run(main_batch_orchestrator_flow())