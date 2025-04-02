from config.config import Config
from tasks.registry import task_registry
import asyncio
from datetime import datetime
from flows.factory.main_flow import create_analysis_flow

ALL_TASKS = [
    "core.lizard",
    "core.cloc",
    "core.goenry",
    "core.gitlog",

    "languages.go.build",
    "languages.java.gradle.build",
    "languages.java.maven.build",
    "languages.javascript.build",
    "languages.python.build",

    "languages.go.dependencies",
    "languages.java.gradle.dependencies",
    "languages.java.maven.dependencies",
    "languages.javascript.dependencies",
    "languages.python.dependencies",

    "core.checkov",
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
    processing_batch_size=Config.DEFAULT_PROCESSING_BATCH_SIZE,
    processing_batch_workers=Config.DEFAULT_PROCESSING_BATCH_WORKERS,
    per_batch_workers=Config.DEFAULT_PER_BATCH_WORKERS,
    task_concurrency=Config.DEFAULT_TASK_CONCURRENCY
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
