import asyncio
import argparse
import logging
from datetime import datetime
from prefect.client.orchestration import get_client
from prefect.filters import FlowRunFilter, TaskRunFilter

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

async def get_parent_run_id(flow_run_name):
    """Fetch the most recent flow run ID for the given name."""
    async with get_client() as client:
        try:
            flow_runs = await client.read_flow_runs(
                filter=FlowRunFilter(name={"any_": [flow_run_name]})
            
            if not flow_runs:
                logging.error(f"No flow runs found with name: {flow_run_name}")
                return None
            
            # Sort runs by start time (most recent first)
            flow_runs.sort(key=lambda run: run.start_time or datetime.min, reverse=True)
            
            if len(flow_runs) > 1:
                logging.warning(f"Multiple runs found. Selecting most recent: {flow_runs[0].id}")
            
            parent_run_id = flow_runs[0].id
            logging.info(f"Parent flow run ID: {parent_run_id}")
            return parent_run_id
        
        except Exception as e:
            logging.error(f"Error fetching parent run: {e}")
            return None

async def get_subflow_count(parent_run_id):
    """Count subflows triggered by the parent flow's tasks."""
    async with get_client() as client:
        try:
            # Fetch tasks from the parent flow run
            task_runs = await client.read_task_runs(
                filter=TaskRunFilter(flow_run_id={"any_": [parent_run_id]}))
            
            parent_task_ids = {task.id for task in task_runs}
            logging.info(f"Parent tasks: {len(parent_task_ids)}")
            
            if not parent_task_ids:
                return 0
            
            # Fetch subflows triggered by these tasks
            subflows = await client.read_flow_runs(
                filter=FlowRunFilter(triggering_task_run_id={"any_": list(parent_task_ids)})
            )
            logging.info(f"Detected subflows: {len(subflows)}")
            
            for subflow in subflows:
                logging.debug(f"Subflow ID: {subflow.id}, State: {subflow.state.name}")
            
            return len(subflows)
        
        except Exception as e:
            logging.error(f"Error counting subflows: {e}")
            return 0

async def main(flow_run_name):
    parent_run_id = await get_parent_run_id(flow_run_name)
    if parent_run_id is None:
        return
    total_subflows = await get_subflow_count(parent_run_id)
    logging.info(f"Total subflows for '{flow_run_name}': {total_subflows}")
    print(f"Total subflows: {total_subflows}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Count subflows of a Prefect flow run.")
    parser.add_argument("flow_run_name", help="Name of the parent flow run.")
    args = parser.parse_args()
    asyncio.run(main(args.flow_run_name))