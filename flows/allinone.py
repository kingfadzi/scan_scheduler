
from datetime import datetime

from flows.factory import create_analysis_flow

from config.config import Config
from tasks.core_tasks import run_lizard_task, run_cloc_task, run_goenry_task, run_gitlog_task, \
    run_checkov_analysis_task, run_semgrep_analysis_task, run_syft_analysis_task, run_grype_analysis_task, \
    run_trivy_analysis_task, run_xeol_analysis_task
from tasks.go_tasks import run_go_build_tool_task, run_go_dependency_task
from tasks.java_tasks import run_gradlejdk_task, run_mavenjdk_task, run_gradle_dependency_task, \
    run_maven_dependency_task
from tasks.javascript_tasks import run_javascript_build_tool_task, run_javascript_dependency_task
from tasks.python_tasks import run_python_build_tool_task, run_python_dependency_task

sub_tasks = [

    run_lizard_task,
    run_cloc_task,
    run_goenry_task,
    run_gitlog_task,

    run_go_build_tool_task,
    run_gradlejdk_task,
    run_mavenjdk_task,
    run_javascript_build_tool_task,
    run_python_build_tool_task,

    run_go_dependency_task,
    run_gradle_dependency_task,
    run_maven_dependency_task,
    run_javascript_dependency_task,
    run_python_dependency_task,

    run_checkov_analysis_task,
    run_semgrep_analysis_task,

    run_syft_analysis_task,
    run_grype_analysis_task,
    run_trivy_analysis_task,
    run_xeol_analysis_task

]

allinone_flow = create_analysis_flow(
    flow_name="allinone_flow",
    flow_run_name=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    default_sub_tasks=sub_tasks,
    default_sub_dir="allinone",
    default_flow_prefix="ALL",
    default_batch_size=Config.DEFAULT_DB_FETCH_BATCH_SIZE,
    default_concurrency=Config.DEFAULT_CONCURRENCY_LIMIT
)


if __name__ == "__main__":
    allinone_flow({
        "payload": {
            "host_name": [Config.GITLAB_HOSTNAME],
            #"main_language": ["Java"]
        }
    })
