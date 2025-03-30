# build_tools.py
from factory6 import create_analysis_flow
from config.config import Config
from tasks.registry import task_registry  # Correct import path

# Valid task keys based on registry structure
VALID_BUILD_TASKS = [
    "languages.go.build",
    "languages.java.gradle.build",
    "languages.java.maven.build",
    "languages.javascript.build",
    "languages.python.build"
]

# Create the build tools flow
build_tools_flow = create_analysis_flow(
    flow_name="build_tools_flow",
    default_sub_dir="build_tools",
    default_flow_prefix="BUILD_TOOLS",
    default_additional_tasks=VALID_BUILD_TASKS,
    processing_batch_size=10,
    processing_batch_workers=2,
    per_batch_workers=5,
    task_concurrency=3
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
