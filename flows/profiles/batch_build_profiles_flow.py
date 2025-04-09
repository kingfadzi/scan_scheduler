import asyncio
from prefect import flow, get_run_logger
from prefect.deployments import run_deployment
from prefect.task_runners import ConcurrentTaskRunner

PER_BATCH_WORKERS = 5  # Controls parallel execution

@flow(task_runner=ConcurrentTaskRunner(max_workers=PER_BATCH_WORKERS))
async def batch_build_profiles_flow(repo_ids: list[str], batch_number: int):
    logger = get_run_logger()
    logger.info(f"🚀 Starting Batch {batch_number} - {len(repo_ids)} repos")
    
    # Create async tasks for concurrent execution
    tasks = []
    for repo_id in repo_ids:
        tasks.append(
            asyncio.create_task(
                run_deployment(
                    deployment_name="build-profile-flow/build_profile_flow",
                    parameters={"repo_id": repo_id},
                    timeout=0  # Non-blocking
                )
            )
        )
    
    # Execute all deployments concurrently
    await asyncio.gather(*tasks)
    
    logger.info(f"✅ Batch {batch_number} completed - {len(repo_ids)} subflows")

if __name__ == "__main__":
    asyncio.run(
        batch_build_profiles_flow(
            repo_ids=["repo-001", "repo-002"], 
            batch_number=42
        )
    )
