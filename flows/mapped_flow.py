from prefect import flow, get_run_logger
import asyncio

@flow(log_prints=True)
async def process_item(item: int) -> int:
    logger = get_run_logger()
    logger.info(f"Processing item {item}")
    await asyncio.sleep(1)  # Simulate async work
    result = item ** 2
    logger.info(f"Result for {item}: {result}")
    return result

@flow(log_prints=True)
async def parent_flow(items: list[int]):
    logger = get_run_logger()
    logger.info("Starting parent flow")
    
    # Create and gather subflow runs
    tasks = [process_item(item) for item in items]
    results = await asyncio.gather(*tasks)
    
    logger.info(f"All results: {results}")
    return results

if __name__ == "__main__":
    # For local testing
    asyncio.run(parent_flow([1, 2, 3, 4, 5]))