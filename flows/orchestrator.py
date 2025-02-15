from prefect import flow, task
from prefect.client.orchestration import get_client
from typing import Dict, List
import asyncio
from analysis import (
    analyze_fundamentals,
    analyze_vulnerabilities,
    analyze_standards,
    analyze_component_patterns
)

BATCH_SIZE = 500  # ✅ Process repositories in batches

@task
def query_repositories(payload: Dict) -> List[str]:
    """Fetch repositories from database in manageable batches"""
    all_repos = [f"repo-{i}" for i in range(1, 10001)]  # Simulating 10,000 repos
    return [all_repos[i : i + BATCH_SIZE] for i in range(0, len(all_repos), BATCH_SIZE)]  # ✅ Split into batches

async def trigger_flow_run(deployment_name: str, parameters: dict):
    """Creates a new flow run for a deployment in a work pool."""
    async with get_client() as client:
        deployments = await client.read_deployments(name=deployment_name)
        if not deployments:
            raise ValueError(f"Deployment {deployment_name} not found")
        deployment_id = deployments[0].id
        flow_run = await client.create_flow_run(
            deployment_id=deployment_id,
            parameters=parameters
        )
        return flow_run

@flow(name="process_repository", log_prints=True)
async def process_repository(repo_id: str):
    """Runs all analysis flows for a single repository"""

    print(f"🚀 Scheduling analyze_fundamentals for {repo_id}")

    fundamentals_run = await trigger_flow_run("fundamentals", {"repo_id": repo_id})

    print(f"✅ Fundamentals scheduled for {repo_id}, scheduling other analyses...")

    # ✅ Schedule the remaining analyses in parallel
    await asyncio.gather(
        trigger_flow_run("vulnerabilities", {"repo_id": repo_id}),
        trigger_flow_run("standards-compliance", {"repo_id": repo_id}),
        trigger_flow_run("component-patterns", {"repo_id": repo_id}),
    )

    return f"✅ Processing scheduled for {repo_id}"

@flow(name="main_orchestrator", log_prints=True)
async def main_orchestrator(payload: Dict):
    """Main orchestrator flow that batches and queues repository processing"""
    repo_batches = query_repositories(payload)

    for batch in repo_batches:
        print(f"✅ Enqueueing batch of {len(batch)} repositories for processing...")

        # ✅ Deploy each repository for processing asynchronously in its own work pool
        tasks = [trigger_flow_run("process_repository", {"repo_id": repo_id}) for repo_id in batch]
        await asyncio.gather(*tasks)

    print("✅ All repository batches have been scheduled for processing.")

# ✅ Main entry point for local execution
if __name__ == "__main__":
    import asyncio

    sample_payload = {
        "job_id": "local-test-123",
        "repositories": ["repo-1", "repo-2", "repo-3"],
        "config": {"threshold": 95, "mode": "full_scan"}
    }

    print("🚀 Running main_orchestrator locally...")
    asyncio.run(main_orchestrator(payload=sample_payload))  # ✅ Run locally
