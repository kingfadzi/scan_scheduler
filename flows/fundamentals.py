from config.config import Config
import asyncio
from flows.factory.main_flow import create_analysis_flow

VALID_METRICS_TASKS = [
    "core.lizard",
    "core.cloc",
    "core.goenry",
    "core.gitlog"
]

fundamental_metrics_flow = create_analysis_flow(
    flow_name="fundamental_metrics_flow",
    default_sub_dir="fundamental_metrics",
    default_flow_prefix="METRICS",
    default_additional_tasks=VALID_METRICS_TASKS,
    default_db_fetch_batch_size=Config.DEFAULT_DB_FETCH_BATCH_SIZE,
    default_processing_batch_size=Config.DEFAULT_PROCESSING_BATCH_SIZE,
    default_processing_batch_workers=Config.DEFAULT_PROCESSING_BATCH_WORKERS,
    default_per_batch_workers=Config.DEFAULT_PER_BATCH_WORKERS,
    default_task_concurrency=Config.DEFAULT_TASK_CONCURRENCY
)

if __name__ == "__main__":
    asyncio.run(fundamental_metrics_flow(
        payload={
            "payload": {
                "host_name": [Config.GITLAB_HOSTNAME, Config.BITBUCKET_HOSTNAME],
                #"activity_status": ['ACTIVE'],
                # "main_language": ["Python"]
            }
        }
    ))
