from datetime import datetime

from flows.factory import create_analysis_flow

from config.config import Config
from tasks.go_tasks import run_go_dependency_task
from tasks.java_tasks import run_gradle_dependency_task, run_maven_dependency_task
from tasks.javascript_tasks import run_javascript_dependency_task
from tasks.python_tasks import run_python_dependency_task

sub_tasks = [
    run_go_dependency_task,
    run_gradle_dependency_task,
    run_maven_dependency_task,
    run_javascript_dependency_task,
    run_python_dependency_task
]

dependencies_flow = create_analysis_flow(
    flow_name="build_tools_and_dependencies_flow",
    flow_run_name=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    default_sub_tasks=sub_tasks,
    default_sub_dir="build_tools_and_dependencies_flow",
    default_flow_prefix="DEPENDENCIES",
    default_batch_size=Config.DEFAULT_DB_FETCH_BATCH_SIZE,
    default_concurrency=Config.DEFAULT_CONCURRENCY_LIMIT
)


if __name__ == "__main__":
    dependencies_flow({
        "payload": {
            "host_name": [Config.GITLAB_HOSTNAME],
            #"main_language": ["Java"]
        }
    })
