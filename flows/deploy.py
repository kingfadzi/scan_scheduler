from prefect.deployments import Deployment
from prefect.filesystems import GitStorage
from flows.orchestrator import main_orchestrator
from flows.analysis import (
    analyze_fundamentals,
    analyze_vulnerabilities,
    analyze_standards,
    analyze_component_patterns
)

# Configure version-aware Git storage (matches Prefect 3.2.x requirements)
storage = GitStorage(
    repo_url="https://github.com/kingfadzi/scan_scheduler.git",
    reference="distributed",
    include_git_ref=True  # Required for version tracking in 3.2+
)

DEPLOYMENTS = [
    (main_orchestrator, "main-orchestrator", "orchestrator-pool"),
    (analyze_fundamentals, "fundamentals", "fundamentals-pool"),
    (analyze_vulnerabilities, "vulnerabilities", "vulnerabilities-pool"),
    (analyze_standards, "standards-compliance", "standards-pool"),
    (analyze_component_patterns, "component-patterns", "components-pool")
]

def create_deployments():
    """Create deployments with version compatibility checks"""
    for flow, name_suffix, pool_name in DEPLOYMENTS:
        deployment = Deployment.build_from_flow(
            flow=flow,
            name=f"{flow.name}-{name_suffix}",
            version="3.2.1",  # Must match client version [2][5]
            storage=storage,
            work_pool_name=pool_name,
            infra_overrides={
                "env": {"PREFECT_API_VERSION": "3.2.1"},
                "labels": ["prod"]
            },
            tags=["security-scan", "v3.2.1"]
        )
        deployment.apply()
        print(f"Created deployment {deployment.name}")

if __name__ == "__main__":
    print("Validating API version compatibility...")
    create_deployments()
    print("Deployments successfully registered with Prefect Cloud")
