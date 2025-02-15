from prefect import flow, task
from typing import Dict, List
import asyncio
from analysis import (
    analyze_fundamentals,
    analyze_vulnerabilities,
    analyze_standards,
    analyze_component_patterns
)

BATCH_SIZE = 500  # ✅ Process repositories in batches to avoid memory overload

@task
def query_repositories(payload: Dict) -> List[str]:
    """Fetch repositories from database in manageable batches"""
    all_repos = [f"repo-{i}" for i in range(1, 10001)]  # Simulating 10,000 repos
    return [all_repos[i : i + BATCH_SIZE] for i in range(0, len(all_repos), BATCH_SIZE)]  # ✅ Split into batches

@flow(name="process_repository", log_prints=True)
def process_repository(repo_id: str):
    """Runs all analysis flows for a single repository"""
    fundamentals_result = analyze_fundamentals(repo_id)
    
    if fundamentals_result != "Completed":
        raise RuntimeError(f"Fundamentals failed for {repo_id}, stopping execution.")

    analyze_vulnerabilities(repo_id)
    analyze_standards(repo_id)
    analyze_component_patterns(repo_id)

    return f"Processing complete for {repo_id}"

@flow(name="main_orchestrator", log_prints=True)
async def main_orchestrator(payload: Dict):
    """Main orchestrator flow that batches and queues repository processing"""
    repo_batches = query_repositories(payload)

    for batch in repo_batches:
        print(f"✅ Enqueueing batch of {len(batch)} repositories for processing...")

        # ✅ Fix: Use `.call()` for flows instead of `.submit()`
        tasks = [process_repository.call(repo_id) for repo_id in batch]

        await asyncio.sleep(2)  # ✅ Prevent overwhelming the scheduler with 1000s of simultaneous runs

    print("✅ All repository batches have been scheduled for processing.")