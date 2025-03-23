from config.config import Config
from datetime import datetime
from flows.factory import create_analysis_flow
from tasks.core_tasks import run_lizard_task, run_cloc_task, run_goenry_task, run_gitlog_task

sub_tasks = [
    run_lizard_task,
    run_cloc_task,
    run_goenry_task,
    run_gitlog_task
]

fundamental_metrics_flow = create_analysis_flow(
    flow_name="fundamental_metrics_flow",
    flow_run_name=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    default_sub_tasks=sub_tasks,
    default_sub_dir="fundamental_metric",
    default_flow_prefix="METRICS",
    default_batch_size=Config.DEFAULT_DB_FETCH_BATCH_SIZE,
    default_concurrency=Config.DEFAULT_CONCURRENCY_LIMIT
)


if __name__ == "__main__":
    fundamental_metrics_flow({
        "payload": {
            "host_name": [Config.GITLAB_HOSTNAME],
            "main_language": ["Java"]
        }
    })
