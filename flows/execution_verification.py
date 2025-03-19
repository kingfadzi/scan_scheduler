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

async def count_subflows(parent_run_id):
    """Count the total number of subflows for the given parent flow run ID."""
    async with get_client() as client:
        flow_runs = await client.read_flow_runs(parent_flow_run_id=parent_run_id)
        return len(flow_runs)

async def main(flow_run_name):
    parent_run_id = await get_parent_run_id(flow_run_name)
    if parent_run_id:
        total_subflows = await count_subflows(parent_run_id)
        print(f"Total subflows for '{flow_run_name}': {total_subflows}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Count subflows for a given flow run name.")
    parser.add_argument("flow_run_name", help="The name of the parent flow run.")
    args = parser.parse_args()

    asyncio.run(main(args.flow_run_name))