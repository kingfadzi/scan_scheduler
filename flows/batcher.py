import asyncio
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
MAX_PARALLEL_BATCHES = 2
REPOS_PER_BATCH = 100

# --- DB Helper function
def fetch_repo_chunk(last_seen_repo_id: str | None, limit: int) -> list[str]:
    with SessionLocal() as session:
        query = session.query(Repository.repo_id).order_by(Repository.repo_id)
        if last_seen_repo_id:
            query = query.filter(Repository.repo_id > last_seen_repo_id)
        rows = query.limit(limit).all()
        return [r.repo_id for r in rows]

# --- Main Orchestrator Flow
@flow(task_runner=ConcurrentTaskRunner(max_workers=MAX_PARALLEL_BATCHES))
async def main_batch_orchestrator_flow():
    processed = 0
    last_seen_repo_id = None
    batch_futures = []

    async with get_client() as client:
        # Fetch the batch deployment
        deployment = await client.read_deployment_by_name(
            "build-profile-flow/Batch Build Profiles"
        )

        while True:
            batch_repo_ids = fetch_repo_chunk(last_seen_repo_id, REPOS_PER_BATCH)

            if not batch_repo_ids:
                break

            batch_number = (processed // REPOS_PER_BATCH) + 1

            # Launch batch by deployment ID
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

# --- Launcher
if __name__ == "__main__":
    asyncio.run(main_batch_orchestrator_flow())