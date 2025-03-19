import asyncio
import argparse
import logging
from prefect.client.orchestration import get_client

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")

async def get_parent_run_id(flow_run_name):
    """Fetch the flow run ID for the given flow run name."""
    async with get_client() as client:
        # Retrieve all flow runs
        flow_runs = await client.read_flow_runs()
        
        # Log available flow runs
        logging.debug(f"Total flow runs retrieved: {len(flow_runs)}")
        
        # Filter flow runs by name
        matching_runs = [run for run in flow_runs if run.name == flow_run_name]

        if not matching_runs:
            logging.error(f"No flow runs found with name: {flow_run_name}")
            return None

        parent_run_id = matching_runs[0].id
        logging.info(f"Found parent flow run ID: {parent_run_id} for name: {flow_run_name}")
        return parent_run_id

async def get_subflow_count(parent_run_id):
    """Count the total number of subflows based on parent task runs."""
    async with get_client() as client:
        # Fetch all task runs
        task_runs = await client.read_task_runs()
        logging.debug(f"Total task runs retrieved: {len(task_runs)}")

        # Filter task runs belonging to the parent flow run
        parent_task_run_ids = {task.id for task in task_runs if task.flow_run_id == parent_run_id}
        logging.info(f"Task runs found for parent flow run ID {parent_run_id}: {parent_task_run_ids}")

        # Fetch all flow runs
        flow_runs = await client.read_flow_runs()
        logging.debug(f"Total flow runs retrieved (again): {len(flow_runs)}")

        # Filter for subflows
        subflows = [run for run in flow_runs if run.parent_task_run_id in parent_task_run_ids]
        logging.info(f"Detected {len(subflows)} subflows for parent flow run ID {parent_run_id}")

        # Log details of detected subflows
        for subflow in subflows:
            logging.debug(f"Subflow detected - ID: {subflow.id}, Name: {subflow.name}")

        return len(subflows)

async def main(flow_run_name):
    parent_run_id = await get_parent_run_id(flow_run_name)
    if parent_run_id:
        total_subflows = await get_subflow_count(parent_run_id)
        logging.info(f"Total subflows for '{flow_run_name}': {total_subflows}")
        print(f"Total subflows for '{flow_run_name}': {total_subflows}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Count subflows for a given flow run name.")
    parser.add_argument("flow_run_name", help="The name of the parent flow run.")
    args = parser.parse_args()

    asyncio.run(main(args.flow_run_name))