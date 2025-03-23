
from config.config import Config
from flows.factory import create_analysis_flow
from datetime import datetime

from tasks.core_tasks import run_trivy_analysis_task, run_syft_analysis_task, run_grype_analysis_task, \
    run_xeol_analysis_task

sub_tasks = [
    run_syft_analysis_task,
    run_grype_analysis_task,
    run_trivy_analysis_task,
    run_xeol_analysis_task
]


vulnerabilities_flow = create_analysis_flow(
    flow_name="vulnerabilities_flow",
    flow_run_name=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    default_sub_tasks=sub_tasks,
    default_sub_dir="vulnerabilities",
    default_flow_prefix="VULN",
    default_batch_size=Config.DEFAULT_DB_FETCH_BATCH_SIZE,
    default_concurrency=Config.DEFAULT_CONCURRENCY_LIMIT
)


if __name__ == "__main__":
    vulnerabilities_flow({
        "payload": {
            "host_name": [Config.GITLAB_HOSTNAME],
            "main_language": ["Java"]
        }
    })
