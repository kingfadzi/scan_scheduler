import asyncio
import random
from prefect import flow, task
from prefect.task_runners import ConcurrentTaskRunner

# Parameters
PER_BATCH_WORKERS = 10         # 10 concurrent repo subflows inside each batch
REPOS_PER_BATCH = 100          # 100 repos per batch
TOTAL_BATCHES = 10             # 10 batches
SIMULATED_SLEEP_RANGE = (1, 2) # 1-2 seconds sleep per repo

# --- Simulated build task (per repo)
@task
async def simulate_build_profile(repo_id: str, batch_number: int):
    print(f"[Batch {batch_number}] Starting repo {repo_id}")
    await asyncio.sleep(random.uniform(*SIMULATED_SLEEP_RANGE))
    print(f"[Batch {batch_number}] Completed repo {repo_id}")

# --- Per-repo subflow
@flow
async def build_profile_flow(repo_id: str, batch_number: int):
    await simulate_build_profile(repo_id, batch_number)

# --- Batch flow
@flow(task_runner=ConcurrentTaskRunner(max_workers=PER_BATCH_WORKERS))
async def batch_build_profiles_flow(repo_ids: list[str], batch_number: int):
    for repo_id in repo_ids:
        build_profile_flow(repo_id=repo_id, batch_number=batch_number)

# --- Top-level launcher
@flow
async def main_batch_orchestrator_flow():
    batch_futures = []

    for batch_number in range(1, TOTAL_BATCHES + 1):
        # Create fake repo ids for this batch
        batch_repo_ids = [f"repo-{batch_number}-{i+1}" for i in range(REPOS_PER_BATCH)]

        # Launch batch flow asynchronously
        batch_future = asyncio.create_task(
            batch_build_profiles_flow(repo_ids=batch_repo_ids, batch_number=batch_number)
        )
        batch_futures.append(batch_future)

    await asyncio.gather(*batch_futures)
    print("All batches completed.")

# --- Run if script
if __name__ == "__main__":
    asyncio.run(main_batch_orchestrator_flow())