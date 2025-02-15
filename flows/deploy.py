from orchestrator import main_orchestrator
from analysis import (
    analyze_fundamentals,
    analyze_vulnerabilities,
    analyze_standards,
    analyze_component_patterns
)

# Repository and deployment configuration
REPO_URL = "https://github.com/kingfadzi/scan_scheduler.git"
BRANCH = "distributed"
DEPLOYMENT_VERSION = "3.2.1"

# Map each flow to its work pool (or work queue) name
DEPLOYMENTS = [
    (main_orchestrator, "main-orchestrator", "orchestrator-pool"),
    (analyze_fundamentals, "fundamentals", "fundamentals-pool"),
    (analyze_vulnerabilities, "vulnerabilities", "vulnerabilities-pool"),
    (analyze_standards, "standards-compliance", "standards-pool"),
    (analyze_component_patterns, "component-patterns", "components-pool")
]

def create_deployments():
    for flow, name_suffix, pool_name in DEPLOYMENTS:
        deployment_name = f"{flow.name}-{name_suffix}"
        # Deploy the flow using the new API.
        flow.deploy(
            name=deployment_name,
            version=DEPLOYMENT_VERSION,
            work_pool_name=pool_name,
            tags=["security-scan", f"v{DEPLOYMENT_VERSION}"],
            git_repo=REPO_URL,
            git_branch=BRANCH
        )
        print(f"Created deployment {deployment_name}")

if __name__ == "__main__":
    print("Deploying flows...")
    create_deployments()
    print("Deployments successfully registered with Prefect Cloud")