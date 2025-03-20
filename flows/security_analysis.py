from prefect import flow, task, get_run_logger
from flows.factory import create_analysis_flow

from prefect import task
from config.config import Config


@task(name="Security Scan")
def security_scan(repo: dict, run_id: str):
    logger = get_run_logger()
    logger.info(f"[{run_id}] Scanning {repo['repo_id']}")
    # Security scanning logic here


security_analysis_flow = create_analysis_flow(
    flow_name="security_analysis_flow",
    default_sub_tasks=[security_scan],
    default_sub_dir="security_scans",
    default_flow_prefix="SEC",
    default_batch_size=10,
    default_concurrency=5
)


if __name__ == "__main__":
    security_analysis_flow({
        "payload": {
            "host_name": [Config.GITLAB_HOSTNAME],
            "main_language": ["Java"]
        }
    })
