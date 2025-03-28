#!/usr/bin/env python
import os
from prefect import flow
from prefect.runner.storage import GitRepository
from config.config import Config

# Allow Git to bypass strict host key checking
os.environ["GIT_SSH_COMMAND"] = "ssh -o StrictHostKeyChecking=no"

# Define Git-backed storage so flows are loaded from your repository
git_storage = GitRepository(
    url=Config.FLOW_GIT_STORAGE,
    branch=Config.FLOW_GIT_BRANCH,  # Use the desired branch
)

DEPLOYMENT_VERSION = "3.2.1"

# Define deployments as tuples of (entrypoint, deployment name, work pool name)
DEPLOYMENTS = [
    ("flows/factory4.py:process_single_repo_flow", "process_single_repo_flow-deoployment", "fundamentals-pool"),
    ("flows/factory4.py:batch_repo_subflow", "batch_repo_subflow-deployment", "fundamentals-pool"),
    ("flows/factory4.py:main_flow", "main_flow-deployment", "fundamentals-pool"),
    ("flows/build_tools.py:build_tools_flow", "build_tools_flow", "fundamentals-pool")
]

def create_deployments():
    for entrypoint, deployment_name, pool_name in DEPLOYMENTS:
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
