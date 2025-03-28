# build_tools.py
from factory4 import create_analysis_flow
from config.config import Config

# Map task function registry keys (example mapping)
TASK_REGISTRY_KEYS = {
    "run_go_build_tool_task": "go",
    "run_gradlejdk_task": "gradle",
    "run_mavenjdk_task": "maven",
    "run_javascript_build_tool_task": "js",
    "run_python_build_tool_task": "python"
}

# Convert the original task list to registry keys
sub_tasks = [TASK_REGISTRY_KEYS[key] for key in [
    "run_go_build_tool_task",
    "run_gradlejdk_task",
    "run_mavenjdk_task",
    "run_javascript_build_tool_task",
    "run_python_build_tool_task"
]]

# Create the build tools flow using the factory
build_tools_flow = create_analysis_flow(
    flow_name="build_tools_flow",
    default_sub_dir="build_tools",
    default_flow_prefix="BUILD_TOOLS",
    default_additional_tasks=["python", "gradle"],
    processing_batch_size=10,
    processing_batch_workers=2,  # Max concurrent batches
    per_batch_workers=5,         # Max repos per batch
    task_concurrency=3           # Max tasks per repo
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
