from config.config import Config
import asyncio
from flows.factory.main_flow import create_analysis_flow

ALL_TASKS = [
    "core.lizard",
    "core.cloc",
    "core.goenry",
    "core.gitlog",

    "core.syft_dependency"

    "core.iac_components",
    "core.semgrep",

    "core.trivy",
    "core.grype",
    "core.xeol"
]

uber_flow = create_analysis_flow(
    flow_name="uber_flow",
    default_sub_dir="uber",
    default_flow_prefix="UBER",
    default_additional_tasks=ALL_TASKS,
    default_processing_batch_size=Config.DEFAULT_PROCESSING_BATCH_SIZE,
    default_db_fetch_batch_size=Config.DEFAULT_DB_FETCH_BATCH_SIZE,
    default_processing_batch_workers=Config.DEFAULT_PROCESSING_BATCH_WORKERS,
    default_per_batch_workers=Config.DEFAULT_PER_BATCH_WORKERS,
    default_task_concurrency=Config.DEFAULT_TASK_CONCURRENCY
)

if __name__ == "__main__":
    asyncio.run(uber_flow(
        payload={
            "payload": {
                "host_name": [Config.GITLAB_HOSTNAME, Config.BITBUCKET_HOSTNAME],
                'activity_status': ['ACTIVE']
            }
        }
    ))
