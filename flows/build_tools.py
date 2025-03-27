from datetime import datetime
import asyncio
from flows.factory2 import create_analysis_flow
from config.config import Config

# Map task functions to their registry names
TASK_REGISTRY_KEYS = {
    "run_go_build_tool_task": "go",
    "run_gradlejdk_task": "gradle",
    "run_mavenjdk_task": "maven",
    "run_javascript_build_tool_task": "js",
    "run_python_build_tool_task": "python"
}

# Convert original task list to registry keys
sub_tasks = [
    TASK_REGISTRY_KEYS["run_go_build_tool_task"],
    TASK_REGISTRY_KEYS["run_gradlejdk_task"],
    TASK_REGISTRY_KEYS["run_mavenjdk_task"], 
    TASK_REGISTRY_KEYS["run_javascript_build_tool_task"],
    TASK_REGISTRY_KEYS["run_python_build_tool_task"]
]

# Create flow with registered task names
build_tools_flow = create_analysis_flow(
    flow_name="build_tools_flow",
    default_sub_dir="build_tools",
    default_flow_prefix="BUILD_TOOLS",
    default_additional_tasks=sub_tasks,
    default_batch_size=Config.DEFAULT_DB_FETCH_BATCH_SIZE
)

async def main():
    result = await build_tools_flow(
        payload={
            "payload": {
                "host_name": [Config.GITLAB_HOSTNAME],
                # "main_language": ["Java"]  # Uncomment if needed
            }
        }
    )
    print(f"Flow result: {result}")
if __name__ == "__main__":
    asyncio.run(main())