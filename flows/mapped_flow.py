from prefect import flow, get_run_logger
from prefect.deployments import Deployment
from prefect.server.schemas.schedules import IntervalSchedule
from datetime import timedelta
import asyncio

# Subflow definition
@flow(log_prints=True)
async def process_item(item: int) -> int:
    logger = get_run_logger()
    logger.info(f"Processing item {item}")
    await asyncio.sleep(1)  # Simulate work
    result = item ** 2
    logger.info(f"Result for {item}: {result}")
    return result

# Parent flow
@flow(log_prints=True)
async def parent_flow(items: list[int]):
    logger = get_run_logger()
    logger.info("Starting parent flow")
    
    # Create subflow runs concurrently
    coroutines = [process_item(item) for item in items]
    results = await asyncio.gather(*coroutines)
    
    logger.info(f"All results: {results}")
    return results

# Deployment configuration
def deploy():
    deployment = Deployment.build_from_flow(
        flow=parent_flow,
        name="parallel-processing",
        schedule=IntervalSchedule(interval=timedelta(minutes=5)),
        work_pool_name="my-process-pool",
        tags=["demo"]
    )
    deployment.apply()

if __name__ == "__main__":
    # To run locally for testing:
    asyncio.run(parent_flow([1, 2, 3, 4, 5]))
    
    # To deploy to server:
    # deploy()