from prefect import flow, task
from prefect.client.orchestration import get_client
from typing import Dict, List
from analysis import (  # ✅ Ensure all analysis flows are properly imported
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
    
    # Step 1️⃣: Process all fundamentals first **sequentially**
    fundamentals_runs = []
    for repo_id in repos:
        run = analyze_fundamentals(repo_id)  # ✅ Call subflow normally
        fundamentals_runs.append(run)

    # Wait for all fundamentals runs to finish
    for run in fundamentals_runs:
        await run  # ✅ Wait for completion of fundamental metrics

    # Step 2️⃣: Trigger the remaining analyses in parallel
    async with get_client() as client:
        parallel_runs = []
        
        for repo_id in repos:
            parallel_runs.append(analyze_vulnerabilities(repo_id))  # ✅ Run in parallel
            parallel_runs.append(analyze_standards(repo_id))
            parallel_runs.append(analyze_component_patterns(repo_id))

        # Wait for all parallel tasks to complete
        for run in parallel_runs:
            await run

    print("✅ All fundamental and tiger analysis tasks completed successfully.")