from prefect import flow, task, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner
from typing import List

# Define a subflow to process individual items
@flow(log_prints=True)
def process_item(item: int) -> int:
    logger = get_run_logger()
    logger.info(f"Processing item {item}")
    result = item ** 2
    logger.info(f"Result for {item}: {result}")
    return result

# Parent flow that maps the subflow
@flow(task_runner=ConcurrentTaskRunner(), log_prints=True)
def parent_flow(items: List[int]):
    logger = get_run_logger()
    logger.info("Starting parent flow")
    
    # Map the subflow across all items
    results = process_item.map(items)
    
    logger.info(f"All results: {results}")
    return results

if __name__ == "__main__":
    # Test with sample data
    parent_flow([1, 2, 3, 4, 5])