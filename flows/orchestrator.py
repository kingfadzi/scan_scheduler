from prefect import flow, task
from prefect.client.orchestration import get_client
from typing import Dict, List
from analysis import (  # ✅ Explicitly import analysis functions
    analyze_fundamentals,
    analyze_vulnerabilities,
    analyze_standards,
    analyze_component_patterns
)

@task
def query_repositories(payload: Dict) -> List[str]:
    """Fetch repositories from database"""
    # Replace with actual database query
    return [f"repo-{i}" for i in range(1, 4)]

@flow(name="main_orchestrator")
async def main_orchestrator(payload: Dict):
    """Main orchestration flow"""
    repos = query_repositories(payload)
    
    # Process all fundamentals first
    fundamentals_runs = []
    for repo_id in repos:
        run = await analyze_fundamentals.with_options(
            name=f"fundamentals-{repo_id}"  # ✅ Remove 'work_pool_name' here
        ).submit(repo_id)
        fundamentals_runs.append(run)
    
    # Wait for all fundamentals to complete
    for run in fundamentals_runs:
        await run.wait()

    # Process other analyses in parallel
    async with get_client() as client:
        for repo_id in repos:
            await analyze_vulnerabilities.with_options(
                name=f"vulnerabilities-{repo_id}"  # ✅ Fix 'work_pool_name' issue
            ).submit(repo_id)
            await analyze_standards.with_options(
                name=f"standards-{repo_id}"
            ).submit(repo_id)
            await analyze_component_patterns.with_options(
                name=f"components-{repo_id}"
            ).submit(repo_id)