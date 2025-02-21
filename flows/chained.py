import asyncio
from prefect import flow
from prefect.deployments import run_deployment

# Correct deployment names using "<FLOW_NAME>/<DEPLOYMENT_NAME>" format
DEPLOYMENTS = [
    "fundamental_metrics_flow/fundamentals",
    "component_patterns_flow/component-patterns",
    "vulnerabilities_flow/vulnerabilities",
    "standards_assessment_flow/standards-assessment"
]

# Example payload to pass to each deployment
example_payload = {
    "payload": {
        "host_name": ["github.com"],
        "activity_status": ["ACTIVE"],
        "main_language": ["Python"]
    }
}

@flow(name="Flow Orchestrator")
async def flow_orchestrator():
    """Sequentially triggers each Prefect deployment as an independent top-level flow run."""
    
    for deployment_name in DEPLOYMENTS:
        print(f"Triggering deployment: {deployment_name} with payload: {example_payload}...")

        # Run the deployment asynchronously with the payload
        flow_run = await run_deployment(name=deployment_name, parameters=example_payload)
        
        # Wait for the deployment to complete before proceeding
        await flow_run.wait_for_completion()

        print(f"Deployment {deployment_name} completed with status: {flow_run.state_name}")

if __name__ == "__main__":
    print("Starting Flow Orchestrator...")
    asyncio.run(flow_orchestrator())
    print("All flows completed.")