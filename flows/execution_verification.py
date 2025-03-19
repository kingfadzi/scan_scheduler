import asyncio
import argparse
from prefect.client.orchestration import get_client

async def get_parent_run_id(flow_run_name):
    """Fetch the flow run ID for the given flow run name."""
    async with get_client() as client:
        # Retrieve all flow runs and filter by name
        flow_runs = await client.read_flow_runs()
        matching_runs = [run for run in flow_runs if run.name == flow_run_name]

        if not matching_runs:
            print(f"No flow runs found with name: {flow_run_name}")
            return None

        return matching_runs[0].id  # Assume first match is correct

async def get_subflow_count(parent_run_id):
    """Count the total number of subflows based on parent task runs."""
    async with get_client() as client:
        # Fetch all task runs and filter those belonging to the parent flow run
        task_runs = await client.read_task_runs()
        parent_task_run_ids = {task.id for task in task_runs if task.flow_run_id == parent_run_id}

        # Fetch all flow runs and filter for subflows
        flow_runs = await client.read_flow_runs()
        subflows = [run for run in flow_runs if run.parent_task_run_id in parent_task_run_ids]

        return len(subflows)

async def main(flow_run_name):
    parent_run_id = await get_parent_run_id(flow_run_name)
    if parent_run_id:
        total_subflows = await get_subflow_count(parent_run_id)
        print(f"Total subflows for '{flow_run_name}': {total_subflows}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Count subflows for a given flow run name.")
    parser.add_argument("flow_run_name", help="The name of the parent flow run.")
    args = parser.parse_args()

    asyncio.run(main(args.flow_run_name))