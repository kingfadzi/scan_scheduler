from prefect import flow
from prefect.runner.storage import GitRepository

# Define Git storage
git_storage = GitRepository(
    url="https://github.com/kingfadzi/scan_scheduler.git",
    branch="distributed"
)

DEPLOYMENTS = [
    ("flows/orchestrator.py:main_orchestrator", "main-orchestrator", "orchestrator-pool"),
    ("flows/analysis.py:analyze_fundamentals", "fundamentals", "fundamentals-pool"),
    ("flows/analysis.py:analyze_vulnerabilities", "vulnerabilities", "vulnerabilities-pool"),
    ("flows/analysis.py:analyze_standards", "standards-compliance", "standards-pool"),
    ("flows/analysis.py:analyze_component_patterns", "component-patterns", "components-pool")
]

def create_deployments():
    for entrypoint, name_suffix, pool_name in DEPLOYMENTS:
        deployment_name = f"{name_suffix}"
        remote_flow = flow.from_source(source=git_storage, entrypoint=entrypoint)

        # ✅ Use `serve()` for Prefect 3.2.1
        remote_flow.serve(
            name=deployment_name,
            work_pool_name=pool_name,
            tags=["security-scan"]
        )
        print(f"✅ Created deployment: {deployment_name}")

if __name__ == "__main__":
    print("🚀 Deploying flows...")
    create_deployments()
    print("🎉 Deployments successfully registered!")
