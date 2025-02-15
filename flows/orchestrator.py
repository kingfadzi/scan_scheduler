from prefect import flow, task
from prefect.client.orchestration import get_client
from typing import Dict, List
from analysis import (  
    analyze_fundamentals,
    analyze_vulnerabilities,
    analyze_standards,
    analyze_component_patterns
)

@task
def query_repositories(payload: Dict) -> List[str]:
    """Fetch repositories from database"""
    return [f"repo-{i}" for i in range(1, 4)]

@flow(name="main_orchestrator")
async def main_orchestrator(payload: Dict):
    """Main orchestration flow"""
    repos = query_repositories(payload)
    
    # Step 1️⃣: Process all fundamentals first **sequentially**
    fundamentals_runs = []
    for repo_id in repos:
        try:
            run = analyze_fundamentals(repo_id)  # ✅ Call the function
            fundamentals_runs.append(run)
        except Exception as e:
            print(f"❌ Fundamentals failed for {repo_id}: {e}")
            raise  # Stop execution immediately if any fundamentals fail

    # ✅ Fix: Properly check if fundamentals succeeded
    for run in fundamentals_runs:
        if run is None or not isinstance(run, dict) or run.get("state") not in ["Completed", "Success"]:
            print(f"❌ Unexpected result from analyze_fundamentals: {run}")
            raise RuntimeError("One or more fundamental metric runs failed, stopping execution.")

    print("✅ All fundamental metrics completed successfully. Proceeding to other analyses.")

    # Step 2️⃣: Trigger the remaining analyses in parallel **ONLY if Step 1 succeeded**
    async with get_client() as client:
        parallel_runs = []
        
        for repo_id in repos:
            parallel_runs.append(analyze_vulnerabilities(repo_id))  
            parallel_runs.append(analyze_standards(repo_id))
            parallel_runs.append(analyze_component_patterns(repo_id))

        # Wait for all parallel tasks to complete
        for run in parallel_runs:
            await run

    print("✅ All analyses completed successfully.")