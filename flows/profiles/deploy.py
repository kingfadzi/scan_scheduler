import os
from prefect import flow
from prefect.runner.storage import GitRepository
from config.config import Config

os.environ["GIT_SSH_COMMAND"] = "ssh -o StrictHostKeyChecking=no"

git_storage = GitRepository(
    url=Config.FLOW_GIT_STORAGE,
    branch=Config.FLOW_GIT_BRANCH
)

DEPLOYMENT_VERSION = "1.0.0"


WORK_POOL = "fundamentals-pool"

DEPLOYMENTS = [
    (
        "flows/profiles/build_profile_flow.py:build_profile_flow",
        "build_profile_flow",
        WORK_POOL,
        ["build_profile_flow", f"v{DEPLOYMENT_VERSION}"]
    ),
    (
        "flows/profiles/batch_build_profiles_flow.py:batch_build_profiles_flow",
        "batch_build_profiles_flow",
        WORK_POOL,
        ["batch_build_profiles_flow", f"v{DEPLOYMENT_VERSION}"]
    ),
    (
        "flows/profiles/main_flow.py:main_batch_profile_flow",
        "main_batch_profile_flow",
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