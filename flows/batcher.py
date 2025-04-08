import asyncio
import random
from prefect import task, flow
from prefect.task_runners import ConcurrentTaskRunner

# Parameters
PER_BATCH_WORKERS = 10
REPOS_PER_BATCH = 100
TOTAL_BATCHES = 10
SIMULATED_SLEEP_RANGE = (1, 2)

# --- Simulated per-repo task
@task
async def simulate_build_profile(repo_id: str, batch_number: int):
    print(f"[Batch {batch_number}] Starting repo {repo_id}")
    await asyncio.sleep(random.uniform(*SIMULATED_SLEEP_RANGE))
    print(f"[Batch {batch_number}] Completed repo {repo_id}")

# --- Per-repo flow
@flow
async def build_profile_flow(repo_id: str, batch_number: int):
    await simulate_build_profile(repo_id, batch_number)

# --- Batch *ASYNC FUNCTION* (NOT flow)
async def batch_build_profiles_async(batch_repo_ids: list[str], batch_number: int):
    semaphore = asyncio.Semaphore(PER_BATCH_WORKERS)
    futures = []

    async def run_repo(repo_id):
        async with semaphore:
            await build_profile_flow(repo_id=repo_id, batch_number=batch_number)

    for repo_id in batch_repo_ids:
        futures.append(asyncio.create_task(run_repo(repo_id)))

    await asyncio.gather(*futures)

# --- Top orchestrator
async def main_batch_orchestrator_flow():
    batch_futures = []

    for batch_number in range(1, TOTAL_BATCHES + 1):
        batch_repo_ids = [f"repo-{batch_number}-{i+1}" for i in range(REPOS_PER_BATCH)]

        # Launch batch asynchronously
        batch_future = asyncio.create_task(
            batch_build_profiles_async(batch_repo_ids, batch_number)
        )
        batch_futures.append(batch_future)

    await asyncio.gather(*batch_futures)
    print("All batches completed.")

# --- Launcher
if __name__ == "__main__":
    asyncio.run(main_batch_orchestrator_flow())