import asyncio
from prefect import flow, get_client
from prefect.deployments import run_deployment
from config.config import Config

# Correct Prefect deployment names (from your deployment list)
DEPLOYMENTS = [
    "fundamental-metrics-flow/fundamentals",
    "component-patterns-flow/component-patterns",
    "standards-assessment-flow/standards-assessment",
    "vulnerabilities-flow/vulnerabilities"
]

# Updated payload (removed 'main_language' to get a larger result set)
example_payload = {
    "payload": {
        "host_name": [Config.GITLAB_HOSTNAME],
        "activity_status": ["ACTIVE"]
    }
}

async def wait_for_flow_completion(flow_run_id):
    """Polls Prefect API to wait for the flow to complete."""
    client = get_client()
    
    while True:
        flow_run = await client.read_flow_run(flow_run_id)
        status = flow_run.state_name

        print(f"Flow run {flow_run_id} status: {status}")

        if status in ["Completed", "Failed", "Cancelled"]:
            print(f"Flow run {flow_run_id} finished with status: {status}")
            return status
        
        await asyncio.sleep(5)  # Poll every 5 seconds

@flow(name="Flow Orchestrator")
async def flow_orchestrator():
    """Sequentially triggers each Prefect deployment as an independent top-level flow run."""
    
    client = get_client()  # Create a Prefect client for API communication

    for deployment_name in DEPLOYMENTS:
        print(f"Triggering deployment: {deployment_name} with payload: {example_payload}...")

        # Run the deployment and get flow run metadata
        flow_run_metadata = await run_deployment(name=deployment_name, parameters=example_payload)
        flow_run_id = flow_run_metadata.id  # Extract the run ID
        
        print(f"Triggered deployment {deployment_name}, waiting for completion (Flow Run ID: {flow_run_id})")

        # Wait for completion before triggering the next flow
        await wait_for_flow_completion(flow_run_id)

if __name__ == "__main__":
    print("Starting Flow Orchestrator...")
    asyncio.run(flow_orchestrator())
    print("All flows completed.")