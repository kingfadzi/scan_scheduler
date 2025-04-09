import asyncio
from prefect import flow, task, get_run_logger
from prefect.deployments import run_deployment
from prefect.task_runners import ConcurrentTaskRunner

PER_BATCH_WORKERS = 5  # Controls concurrent task execution

@task
async def process_repo(repo_id: str, batch_number: int):
    """Task that triggers and tracks individual repo processing flows"""
    logger = get_run_logger()
    try:
        logger.debug(f"🚦 Starting repo {repo_id} (Batch {batch_number})")
        
        # Trigger the deployment-run as a subflow
        await run_deployment(
            name="build-profile-flow/build_profile_flow",
            parameters={"repo_id": repo_id},
            timeout=0  # Non-blocking
        )
        
        logger.info(f"📤 Submitted repo {repo_id} (Batch {batch_number})")
        return True
    except Exception as e:
        logger.error(f"❌ Failed repo {repo_id}: {str(e)}")
        return False

@flow(task_runner=ConcurrentTaskRunner(max_workers=PER_BATCH_WORKERS))
async def batch_build_profiles_flow(repo_ids: list[str], batch_number: int):
    """Main flow that manages concurrent repo processing"""
    logger = get_run_logger()
    logger.info(f"🚀 Starting Batch {batch_number} - {len(repo_ids)} repos")
    
    # Submit all repo processing tasks concurrently
    tasks = [process_repo.submit(repo_id, batch_number) for repo_id in repo_ids]
    
    # Wait for all submissions to complete
    results = await asyncio.gather(*tasks)
    
    # Count successes/failures
    success_count = sum(results)
    failure_count = len(results) - success_count
    
    logger.info(
        f"✅ Batch {batch_number} complete - "
        f"{success_count} succeeded, {failure_count} failed"
    )

if __name__ == "__main__":
    # Example execution
    asyncio.run(
        batch_build_profiles_flow(
            repo_ids=[f"repo-{i:03d}" for i in range(1, 21)],  # 20 test repos
            batch_number=42
        )
    )
