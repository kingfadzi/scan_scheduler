from prefect.filesystems import GitStorage
from flows.orchestrator import main_orchestrator
from flows.analysis import (
    analyze_fundamentals,
    analyze_vulnerabilities,
    analyze_standards,
    analyze_component_patterns
)

# Configure Git storage
storage = GitStorage(
    repo_url="https://github.com/kingfadzi/scan_scheduler.git",
    reference="distributed",
    include_git_ref=True
)

# Define common deployment parameters
DEPLOYMENT_PARAMS = {
    "version": "3.2.1",  # Update as needed
    "storage": storage,
    "work_pool_name": None,  # Will override per flow
    "tags": ["security-scan", "v3.2.1"],
    "env": {"PREFECT_API_VERSION": "3.2.1", "PREFECT_LOGGING_LEVEL": "INFO"},
    "labels": ["prod"]
}

# Map each flow to its deployment-specific parameters
DEPLOYMENTS = [
    (main_orchestrator, "orchestrator-pool"),
    (analyze_fundamentals, "fundamentals-pool"),
    (analyze_vulnerabilities, "vulnerabilities-pool"),
    (analyze_standards, "standards-pool"),
    (analyze_component_patterns, "components-pool")
]

def create_deployments():
    for flow, pool_name in DEPLOYMENTS:
        params = DEPLOYMENT_PARAMS.copy()
        params["work_pool_name"] = pool_name
        # The name can be derived or customized as needed
        deployment_name = f"{flow.name}-{pool_name}"
        
        # Deploy the flow using the new imperative API.
        # Note: The API signature may vary; consult your Prefect version's docs.
        flow.deploy(
            name=deployment_name,
            **params
        )
        print(f"Created deployment {deployment_name}")

if __name__ == "__main__":
    print("Deploying flows...")
    create_deployments()
    print("Deployments successfully registered with Prefect Cloud")