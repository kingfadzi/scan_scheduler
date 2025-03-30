# build_tools.py
from factory6 import create_analysis_flow
from config.config import Config
from tasks.registry.task_registry import task_registry

# Get valid task keys from the registry directly
# build_tools.py
VALID_BUILD_TASKS = [
    "languages.go.build",
    "languages.java.gradle",
    "languages.java.maven",
    "languages.js.build",
    "languages.python.build"
]

# Create flow with corrected task keys
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
    # For local testing, run the flow directly
    asyncio.run(build_tools_flow(
        payload={
            "payload": {  # Outer payload key as required
                "host_name": [Config.GITLAB_HOSTNAME],
            }
        }
    ))
