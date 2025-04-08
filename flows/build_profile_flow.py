from prefect import flow, task
import asyncio
import random

@task
async def simulate_build_profile(repo_id: str, batch_number: int):
    print(f"[Batch {batch_number}] Starting repo {repo_id}")
    await asyncio.sleep(random.uniform(1, 2))
    print(f"[Batch {batch_number}] Completed repo {repo_id}")

@flow
async def build_profile_flow(repo_id: str, batch_number: int):
    await simulate_build_profile(repo_id, batch_number)