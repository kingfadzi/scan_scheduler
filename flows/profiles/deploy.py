import os
from prefect import flow
from prefect.runner.storage import GitRepository
from config.config import Config

# Allow Git to bypass strict host key checking (for private Git repos)
os.environ["GIT_SSH_COMMAND"] = "ssh -o StrictHostKeyChecking=no"

# Git storage settings (adjust your Config class accordingly)
git_storage = GitRepository(
    url=Config.FLOW_GIT_STORAGE,
    branch=Config.FLOW_GIT_BRANCH,
)

# Version for these deployments
DEPLOYMENT_VERSION = "1.0.0"

# Work pool name (adjust if needed)
WORK_POOL = "fundamentals-pool"

# Define deployments: (entrypoint, deployment name, pool name, tags)
DEPLOYMENTS = [
    (
        "flows/profiles/build_profile_flow.py:build_profile_flow",
        "Batch Build Profiles",
        WORK_POOL,
        ["build_profile_flow", f"v{DEPLOYMENT_VERSION}"]
    ),
    (
        "flows/profiles/batch_build_profiles_flow.py:batch_build_profiles_flow",
        "Batch Build Profiles Batch",
        WORK_POOL,
        ["batch_build_profiles_flow", f"v{DEPLOYMENT_VERSION}"]
    ),
    (
        "flows/profiles/main_batch_orchestrator_flow.py:main_batch_orchestrator_flow",
        "Main Batch Orchestrator",
        WORK_POOL,
        ["main_batch_orchestrator_flow", f"v{DEPLOYMENT_VERSION}"]
    ),
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
    print("Deploying profile flows from Git...")
    create_deployments()
    print("Deployments successfully registered!")