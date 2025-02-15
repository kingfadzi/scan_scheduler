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
def main_orchestrator(payload: Dict):
    """Main orchestration flow"""
    repos = query_repositories(payload)

    # Step 1️⃣: Process all fundamentals first **in parallel**
    fundamentals_results = [analyze_fundamentals(repo) for repo in repos]  # ✅ Run subflows in parallel

    # ✅ Ensure all fundamentals completed successfully
    for result in fundamentals_results:
        if result != "Completed":
            print(f"❌ Fundamentals execution failed: {result}")
            raise RuntimeError("One or more fundamental metric runs failed, stopping execution.")

    print("✅ All fundamental metrics completed successfully. Proceeding to other analyses.")

    # Step 2️⃣: Trigger the remaining analyses **in parallel**
    analysis_results = [
        analyze_vulnerabilities(repo) for repo in repos
    ] + [
        analyze_standards(repo) for repo in repos
    ] + [
        analyze_component_patterns(repo) for repo in repos
    ]

    # ✅ Ensure all analyses completed successfully
    for result in analysis_results:
        if result != "Completed":
            print(f"❌ One of the analyses failed: {result}")
            raise RuntimeError("One or more analysis runs failed, stopping execution.")

    print("✅ All analyses completed successfully.")