from prefect import flow
from prefect.runner.storage import GitRepository
from config.config import Config
import os

os.environ["GIT_SSH_COMMAND"] = "ssh -o StrictHostKeyChecking=no"

git_storage = GitRepository(
    url=Config.FLOW_GIT_STORAGE,
    branch=Config.FLOW_GIT_BRANCH,  # Use the correct branch
)

DEPLOYMENT_VERSION = "3.2.1"

DEPLOYMENTS = [
    ("flows/fundamentals.py:fundamental_metrics_flow", "fundamentals", "fundamentals-pool"),
    ("flows/build_tools.py:build_tools_flow", "build_tools", "components-pool"),
    ("flows/dependencies.py:dependencies_flow", "dependencies", "components-pool"),
    ("flows/vulnerabilities.py:vulnerabilities_flow", "vulnerabilities", "vulnerabilities-pool"),
    ("flows/standards.py:standards_assessment_flow", "standards-assessment", "standards-pool"),
    ("flows/categories.py:categories_flow", "categorize_dependencies", "standards-pool")
]

def create_deployments():
    for entrypoint, name_suffix, pool_name in DEPLOYMENTS:
        deployment_name = f"{name_suffix}"
        remote_flow = flow.from_source(
            source=git_storage,
            entrypoint=entrypoint
        )

        remote_flow.deploy(
            name=deployment_name,
            version=DEPLOYMENT_VERSION,
            work_pool_name=pool_name,
            tags=["security-scan", f"v{DEPLOYMENT_VERSION}"]
        )
        print(f"Created deployment: {deployment_name}")

if __name__ == "__main__":
    print("Deploying flows from Git...")
    create_deployments()
    print("Deployments successfully registered with Prefect Cloud!")
