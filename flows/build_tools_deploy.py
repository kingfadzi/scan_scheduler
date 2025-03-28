#!/usr/bin/env python
import os
from prefect import flow
from prefect.runner.storage import GitRepository
from config.config import Config

# Ensure SSH connections use relaxed host key checking
os.environ["GIT_SSH_COMMAND"] = "ssh -o StrictHostKeyChecking=no"

# Configure Git storage so that flows are loaded from your Git repository
git_storage = GitRepository(
    url=Config.FLOW_GIT_STORAGE,
    branch=Config.FLOW_GIT_BRANCH,  # Use the correct branch from your repo
)

DEPLOYMENT_VERSION = "3.2.1"

# Define deployments as tuples of (entrypoint, deployment name, work pool name)
DEPLOYMENTS = [
    # Deploy the dynamic subflow (repo_subflow) defined in factory2.py
    ("floes/factory2.py:repo_subflow", "repo_subflow-deployment", "fundamentals-pool"),
    # Deploy the main build tools flow defined in flows/build_tools.py
    ("flows/build_tools.py:build_tools_flow", "build_tools_flow", "fundamentals-pool")
]

def create_deployments():
    for entrypoint, deployment_name, pool_name in DEPLOYMENTS:
        # Load the remote flow from your Git repository using the specified entrypoint
        remote_flow = flow.from_source(
            source=git_storage,
            entrypoint=entrypoint
        )
        # Deploy the flow. This registers the deployment with Prefect Cloud/Server.
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