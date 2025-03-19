import asyncio
import argparse
import logging
from datetime import datetime
from prefect.client.orchestration import get_client
from prefect.client.schemas.filters import FlowRunFilter, TaskRunFilter  # Correct import path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

async def get_parent_run_id(flow_run_name):
    """Fetch the most recent flow run ID using server-side filtering."""
    async with get_client() as client:
        try:
            flow_runs = await client.read_flow_runs(
                flow_run_filter=FlowRunFilter(name={"any_": [flow_run_name]})  # Fixed parameter name
            
            if not flow_runs:
                logging.error(f"No flow runs found with name: {flow_run_name}")
                return None
            
            flow_runs.sort(key=lambda run: run.start_time or datetime.min, reverse=True)
            if len(flow_runs) > 1:
                logging.warning(f"Multiple runs found. Selecting most recent: {flow_runs[0].id}")
            
            return flow_runs[0].id
        
        except Exception as e:
            logging.error(f"Error fetching parent run: {e}")
            return None

async def get_subflow_count(parent_run_id):
    """Count subflows with proper server-side filtering."""
    async with get_client() as client:
        try:
            # Get parent task IDs
            task_runs = await client.read_task_runs(
                task_run_filter=TaskRunFilter(flow_run_id={"any_": [parent_run_id]})
            
            parent_task_ids = {tr.id for tr in task_runs}
            if not parent_task_ids:
                return 0
            
            # Get subflows triggered by these tasks
            subflows = await client.read_flow_runs(
                flow_run_filter=FlowRunFilter(triggering_task_run_id={"any_": list(parent_task_ids)})
            
            return len(subflows)
        
        except Exception as e:
            logging.error(f"Error counting subflows: {e}")
            return 0

async def main(flow_run_name):
    parent_run_id = await get_parent_run_id(flow_run_name)
    if not parent_run_id:
        return
    count = await get_subflow_count(parent_run_id)
    print(f"Subflows for {flow_run_name}: {count}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("flow_run_name", help="Parent flow run name")
    args = parser.parse_args()
    asyncio.run(main(args.flow_run_name))