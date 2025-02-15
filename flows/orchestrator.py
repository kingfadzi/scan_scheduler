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
        run = analyze_fundamentals.invoke(  # ✅ Use `.invoke()` instead of `.submit()`
            parameters={"repo_id": repo_id}  # Pass parameters correctly
        )
        fundamentals_runs.append(run)
    
    # Wait for all fundamentals to complete
    for run in fundamentals_runs:
        await run.wait()  # ✅ Keep waiting for flows

    # Process other analyses in parallel
    async with get_client() as client:
        for repo_id in repos:
            analyze_vulnerabilities.invoke(parameters={"repo_id": repo_id})  # ✅ Fix calls
            analyze_standards.invoke(parameters={"repo_id": repo_id})
            analyze_component_patterns.invoke(parameters={"repo_id": repo_id})