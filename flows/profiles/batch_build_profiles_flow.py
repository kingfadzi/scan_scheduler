import asyncio
from prefect import flow, get_run_logger
from prefect.deployments import run_deployment
from prefect.task_runners import ConcurrentTaskRunner

PER_BATCH_WORKERS = 5  # Controls parallel subflow execution

@flow(
    task_runner=ConcurrentTaskRunner(max_workers=PER_BATCH_WORKERS),
    persist_result=False  # Recommended for parent flows in Prefect 3
)
async def batch_build_profiles_flow(repo_ids: list[str], batch_number: int):
    """Parent flow that spawns concurrent subflows through deployments"""
    logger = get_run_logger()
    logger.info(f"🚀 Starting Batch {batch_number} - {len(repo_ids)} repos")
    
    # Create async tasks for each subflow
    tasks = []
    for repo_id in repo_ids:
        tasks.append(
            run_deployment.submit(
                deployment_name="build-profile-flow/build_profile_flow",
                parameters={"repo_id": repo_id},
                timeout=0,  # Non-blocking submission
                metadata={"batch": batch_number}  # Custom tracking
            )
        )
    
    # Execute all submissions concurrently
    await asyncio.gather(*tasks)
    
    logger.info(f"✅ Batch {batch_number} - {len(repo_ids)} subflows launched")

if __name__ == "__main__":
    # Example execution
    asyncio.run(
        batch_build_profiles_flow(
            repo_ids=["repo-001", "repo-002", "repo-003"],
            batch_number=42
        )
    )
