import asyncio
import aiohttp
from prefect import flow, get_client
from prefect.deployments import run_deployment
from config.config import Config
from shared.utils import Utils

DEPLOYMENTS = [
    "fundamental-metrics-flow/fundamentals",
    "component-patterns-flow/component-patterns",
    "standards-assessment-flow/standards-assessment",
    "vulnerabilities-flow/vulnerabilities"
]

example_payload = {
    "payload": {
        "host_name": [Config.GITLAB_HOSTNAME, Config.BITBUCKET_HOSTNAME],
        "activity_status": ["ACTIVE"]
    }
}


async def wait_for_flow_completion(flow_run_id):

    client = get_client()

    while True:
        try:
            flow_run = await client.read_flow_run(flow_run_id)
            status = flow_run.state_name

            print(f"Flow run {flow_run_id} status: {status}")

            if status in ["Completed", "Failed", "Cancelled"]:
                if status != "Completed":
                    raise RuntimeError(f"Flow {flow_run_id} failed with status: {status}")
                return status

        except aiohttp.ClientError as e:
            print(f"Error while polling flow {flow_run_id}: {e}")

        await asyncio.sleep(5)  # Poll every 5 seconds

async def run_deployment_with_retries(deployment_name, payload, retries=3):

    for attempt in range(retries):
        try:
            print(f"Attempt {attempt + 1}: Triggering deployment {deployment_name}...")
            flow_run_metadata = await run_deployment(name=deployment_name, parameters=payload)
            return flow_run_metadata.id

        except Exception as e:
            print(f"Error triggering {deployment_name}: {e}")
            if attempt < retries - 1:
                print("Retrying...")
                await asyncio.sleep(5)  # Backoff before retrying
            else:
                raise RuntimeError(f"Deployment {deployment_name} failed after {retries} attempts.")

@flow(name="Flow Orchestrator", flow_run_name=Utils.generate_main_flow_run_name)
async def flow_orchestrator():

    client = get_client()

    for deployment_name in DEPLOYMENTS:
        flow_run_id = await run_deployment_with_retries(deployment_name, example_payload)

        print(f"Triggered deployment {deployment_name}, waiting for completion (Flow Run ID: {flow_run_id})")

        await wait_for_flow_completion(flow_run_id)

if __name__ == "__main__":
    print("Starting Flow Orchestrator...")
    try:
        asyncio.run(flow_orchestrator())
        print("All flows completed successfully.")
    except Exception as e:
        print(f"Orchestration failed: {e}")
        exit(1)
