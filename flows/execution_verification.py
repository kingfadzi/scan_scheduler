import asyncio
import argparse
from prefect.client.orchestration import get_client

async def get_parent_run_id(flow_name):
    """Fetch the latest flow run ID for the given flow name."""
    async with get_client() as client:
        # Get the flow details first to retrieve its ID
        flows = await client.read_flows(name=flow_name)
        if not flows:
            print(f"No flows found with name: {flow_name}")
            return None
        
        flow_id = flows[0].id  # Assuming the first match is the correct one

        # Now get the latest flow run ID
        flow_runs = await client.read_flow_runs(flow_id=flow_id, limit=1)
        if not flow_runs:
            print(f"No flow runs found for flow name: {flow_name}")
            return None

        return flow_runs[0].id

async def count_subflows(parent_run_id):
    """Count the total number of subflows for the given parent flow run ID."""
    async with get_client() as client:
        flow_runs = await client.read_flow_runs(parent_flow_run_id=parent_run_id)
        return len(flow_runs)

async def main(flow_name):
    parent_run_id = await get_parent_run_id(flow_name)
    if parent_run_id:
        total_subflows = await count_subflows(parent_run_id)
        print(f"Total subflows for '{flow_name}': {total_subflows}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Count subflows for a given parent flow name.")
    parser.add_argument("flow_name", help="The name of the parent flow.")
    args = parser.parse_args()

    asyncio.run(main(args.flow_name))