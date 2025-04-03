from config.config import Config
from tasks.registry import task_registry
import asyncio
from datetime import datetime
from flows.factory.main_flow import create_analysis_flow

VALID_SECURITY_TASKS = [
    "core.checkov",
    "core.semgrep"
]

standards_assessment_flow = create_analysis_flow(
    flow_name="standards_assessment_flow",
    default_sub_dir="standards_assessment",
    default_flow_prefix="STAN",
    default_additional_tasks=VALID_SECURITY_TASKS,
    default_processing_batch_size=Config.DEFAULT_PROCESSING_BATCH_SIZE,
    default_processing_batch_workers=Config.DEFAULT_PROCESSING_BATCH_WORKERS,
    default_per_batch_workers=Config.DEFAULT_PER_BATCH_WORKERS,
    default_task_concurrency=Config.DEFAULT_TASK_CONCURRENCY
)

if __name__ == "__main__":
    asyncio.run(standards_assessment_flow(
        payload={
            "payload": {
                "host_name": [Config.GITLAB_HOSTNAME],
                "main_language": ["Java"]
            }
        }
    ))
