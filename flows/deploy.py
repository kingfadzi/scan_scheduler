from prefect import flow
from prefect.runner.storage import GitRepository

# Define Git storage
git_storage = GitRepository(
    url="https://github.com/kingfadzi/scan_scheduler.git",
    branch="distributed"  # Use the correct branch
)

# Deployment configuration
DEPLOYMENT_VERSION = "3.2.1"

# Define flows and their respective work pools
DEPLOYMENTS = [
    ("flows/orchestrator.py:main_orchestrator", "main-orchestrator", "orchestrator-pool"),
    ("flows/fundamentals.py:orchestrate_processing_flow", "fundamentals", "fundamentals-pool"),
    ("flows/analysis.py:analyze_vulnerabilities", "vulnerabilities", "vulnerabilities-pool"),
    ("flows/analysis.py:analyze_standards", "standards-compliance", "standards-pool"),
    ("flows/analysis.py:analyze_component_patterns", "component-patterns", "components-pool")
]

def create_deployments():
    for entrypoint, name_suffix, pool_name in DEPLOYMENTS:
        deployment_name = f"{name_suffix}"

        # Load the flow from Git storage using GitRepository
        remote_flow = flow.from_source(
            source=git_storage,
            entrypoint=entrypoint
        )

        # Deploy the flow
        remote_flow.deploy(
            name=deployment_name,
            version=DEPLOYMENT_VERSION,
            work_pool_name=pool_name,
            tags=["security-scan", f"v{DEPLOYMENT_VERSION}"]
        )
        print(f"✅ Created deployment: {deployment_name}")

if __name__ == "__main__":
    print("🚀 Deploying flows from Git...")
    create_deployments()
    print("🎉 Deployments successfully registered with Prefect Cloud!")
