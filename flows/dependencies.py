from datetime import datetime
import asyncio
from flows.factory7 import create_analysis_flow
from config.config import Config
from tasks.registry import task_registry

VALID_DEPENDENCY_TASKS = [
    "languages.go.dependencies",
    "languages.java.gradle.dependencies",
    "languages.java.maven.dependencies",
    "languages.javascript.dependencies",
    "languages.python.dependencies"
]

dependencies_flow = create_analysis_flow(
    flow_name="dependencies_flow",
    default_sub_dir="dependencies",
    default_flow_prefix="DEPENDENCIES",
    default_additional_tasks=VALID_DEPENDENCY_TASKS,
    processing_batch_size=Config.DEFAULT_PROCESSING_BATCH_SIZE,
    processing_batch_workers=Config.DEFAULT_PROCESSING_BATCH_WORKERS,
    per_batch_workers=Config.DEFAULT_PER_BATCH_WORKERS,
    task_concurrency=Config.DEFAULT_TASK_CONCURRENCY
)


if __name__ == "__main__":

    asyncio.run(dependencies_flow(
        payload={
            "payload": {
                "host_name": [Config.GITLAB_HOSTNAME],
               # "main_language": ["Python"]  # Uncomment if needed
            }
        }
    ))
