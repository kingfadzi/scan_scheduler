from datetime import datetime

from flows.factory import create_analysis_flow
from config.config import Config
from tasks.core_tasks import run_syft_analysis_task, run_grype_analysis_task, run_xeol_analysis_task

sub_tasks = [
    run_syft_analysis_task,
    run_grype_analysis_task,
    run_xeol_analysis_task
]

component_patterns_flow = create_analysis_flow(
    flow_name="component_patterns_flow",
    flow_run_name=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    default_sub_tasks=sub_tasks,
    default_sub_dir="component_patterns",
    default_flow_prefix="COMPOSITION",
    default_batch_size=10,
    default_concurrency=5
)


if __name__ == "__main__":
    component_patterns_flow({
        "payload": {
            "host_name": [Config.GITLAB_HOSTNAME],
            "main_language": ["Java"]
        }
    })
