from config.config import Config
from flows.factory import create_analysis_flow
from datetime import datetime

from tasks.core_tasks import run_checkov_analysis_task, run_semgrep_analysis_task

sub_tasks = [
    run_checkov_analysis_task,
    run_semgrep_analysis_task
]

standards_assessment_flow = create_analysis_flow(
    flow_name="standards_assessment_flow",
    flow_run_name=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    default_sub_tasks=sub_tasks,
    default_sub_dir="standards_assessment",
    default_flow_prefix="STAN",
    default_batch_size=Config.DEFAULT_DB_FETCH_BATCH_SIZE,
    default_concurrency=Config.DEFAULT_CONCURRENCY_LIMIT
)


if __name__ == "__main__":
    standards_assessment_flow({
        "payload": {
            "host_name": [Config.GITLAB_HOSTNAME],
            "main_language": ["Java"]
        }
    })
