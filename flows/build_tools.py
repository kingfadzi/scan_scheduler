
from datetime import datetime

from flows.factory import create_analysis_flow

from config.config import Config
from tasks.go_tasks import run_go_build_tool_task
from tasks.java_tasks import run_gradlejdk_task, run_mavenjdk_task
from tasks.javascript_tasks import run_javascript_build_tool_task
from tasks.python_tasks import run_python_build_tool_task

sub_tasks = [
    run_go_build_tool_task,
    run_gradlejdk_task,
    run_mavenjdk_task,
    run_javascript_build_tool_task,
    run_python_build_tool_task,
]

build_tools_flow = create_analysis_flow(
    flow_name="build_tools_flow",
    flow_run_name=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    default_sub_tasks=sub_tasks,
    default_sub_dir="build_tools",
    default_flow_prefix="BUILD_TOOLS",
    default_batch_size=Config.DEFAULT_DB_FETCH_BATCH_SIZE,
    default_concurrency=Config.DEFAULT_CONCURRENCY_LIMIT
)


if __name__ == "__main__":
    build_tools_flow({
        "payload": {
            "host_name": [Config.GITLAB_HOSTNAME],
            #"main_language": ["Java"]
        }
    })
