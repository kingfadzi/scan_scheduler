import os
from prefect import flow
from prefect.runner.storage import GitRepository
from config.config import Config

# Allow Git to bypass strict host key checking
os.environ["GIT_SSH_COMMAND"] = "ssh -o StrictHostKeyChecking=no"

# Define Git-backed storage so flows are loaded from git repository
git_storage = GitRepository(
    url=Config.FLOW_GIT_STORAGE,
    branch=Config.FLOW_GIT_BRANCH
)

DEPLOYMENT_VERSION = "3.2.1"

DEPLOYMENTS = [
    (
        "flows/factory/single_repo_flow.py:process_single_repo_flow",
        "process_single_repo_flow-deoployment",
        "fundamentals-pool",
        ["process_single_repo_flow", f"v{DEPLOYMENT_VERSION}"]
    ),
    (
        "flows/factory/batch_flow.py:batch_repo_subflow",
        "batch_repo_subflow-deployment",
        "fundamentals-pool",
        ["batch_repo_subflow", f"v{DEPLOYMENT_VERSION}"]
    ),
    (
        "flows/build_tools.py:build_tools_flow",
        "build_tools_flow",
        "fundamentals-pool",
        ["build_tools_flow", f"v{DEPLOYMENT_VERSION}"]
    ),
    (
        "flows/dependencies.py:dependencies_flow",
        "dependencies_flow",
        "fundamentals-pool",
        ["dependencies_flow", f"v{DEPLOYMENT_VERSION}"]
    ),
    (
        "flows/fundamentals.py:fundamental_metrics_flow",
        "fundamental_metrics_flow",
        "fundamentals-pool",
        ["fundamental_metrics_flow", f"v{DEPLOYMENT_VERSION}"]
    ),
     (
        "flows/standards.py:standards_assessment_flow",
        "standards_assessment_flow",
        "fundamentals-pool",
        ["standards_assessment_flow", f"v{DEPLOYMENT_VERSION}"]
    ),
     (
        "flows/vulnerabilities.py:vulnerabilities_flow",
        "vulnerabilities_flow",
        "fundamentals-pool",
        ["vulnerabilities_flow", f"v{DEPLOYMENT_VERSION}"]
    ),
     (
        "flows/categories.py:categories_flow",
        "categories_flow",
        "fundamentals-pool",
        ["categories_flow", f"v{DEPLOYMENT_VERSION}"]
    ),
    (
        "flows/uber.py:uber_flow",
        "uber_flow",
        "fundamentals-pool",
        ["uber_flow", f"v{DEPLOYMENT_VERSION}"]
    )
]

def create_deployments():

    for entrypoint, deployment_name, pool_name, tags in DEPLOYMENTS:
        remote_flow = flow.from_source(
            source=git_storage,
            entrypoint=entrypoint
        )
        remote_flow.deploy(
            name=deployment_name,
            version=DEPLOYMENT_VERSION,
            work_pool_name=pool_name,
            tags=tags
        )
        print(f"Created deployment: {deployment_name}")

if __name__ == "__main__":
    print("Deploying flows from Git...")
    create_deployments()
    print("Deployments successfully registered with Prefect Cloud!")
