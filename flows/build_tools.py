from flows.factory.main_flow import create_analysis_flow
from config.config import Config
from tasks.registry import task_registry

VALID_BUILD_TASKS = [
    "languages.go.build",
    "languages.java.gradle.build",
    "languages.java.maven.build",
    "languages.javascript.build",
    "languages.python.build"
]

build_tools_flow = create_analysis_flow(
    flow_name="build_tools_flow",
    default_sub_dir="build_tools",
    default_flow_prefix="BUILD_TOOLS",
    default_additional_tasks=VALID_BUILD_TASKS,
    default_processing_batch_size=Config.DEFAULT_PROCESSING_BATCH_SIZE,
    default_processing_batch_workers=Config.DEFAULT_PROCESSING_BATCH_WORKERS,
    default_per_batch_workers=Config.DEFAULT_PER_BATCH_WORKERS,
    default_task_concurrency=Config.DEFAULT_TASK_CONCURRENCY
)

if __name__ == "__main__":
    import asyncio
    # Local test payload
    asyncio.run(build_tools_flow(
        payload={
            "payload": {
                "host_name": [Config.GITLAB_HOSTNAME],
            }
        }
    ))
