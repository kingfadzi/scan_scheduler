from prefect.deployments import Deployment
from prefect.filesystems import GitStorage

# Configure Git storage
storage = GitStorage(
    repo_url="https://github.com/kingfadzi/scan_scheduler.git",
    reference="distributed"
)

# Create deployments for each flow
deployments = [
    (
        "main_orchestrator",
        "flows/orchestrator.py:main_orchestrator",
        "orchestrator-pool"
    ),
    (
        "analyze_fundamentals",
        "flows/analysis.py:analyze_fundamentals",
        "fundamentals-pool"
    ),
    (
        "analyze_vulnerabilities",
        "flows/analysis.py:analyze_vulnerabilities",
        "vulnerabilities-pool"
    ),
    (
        "analyze_standards",
        "flows/analysis.py:analyze_standards",
        "standards-pool"
    ),
    (
        "analyze_component_patterns",
        "flows/analysis.py:analyze_component_patterns",
        "components-pool"
    )
]

for name, entrypoint, pool in deployments:
    deployment = Deployment.build_from_flow(
        flow_name=name,
        entrypoint=entrypoint,
        work_pool_name=pool,
        storage=storage,
        apply=True
    )
    deployment.apply()

print("✅ All deployments created successfully")