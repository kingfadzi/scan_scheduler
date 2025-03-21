import asyncio
from prefect import flow, task, get_run_logger
from prefect.cache_policies import NO_CACHE
from config.config import Config
from plugins.common.trivy_analysis import TrivyAnalyzer
from flows.factory import create_analysis_flow
from datetime import datetime


@task(name="Run Trivy Analysis Task", cache_policy=NO_CACHE)
def run_trivy_analysis_task(repo_dir, repo, run_id):

    logger = get_run_logger()
    logger.info(f"[Vulnerabilities] Starting Trivy analysis for repository: {repo['repo_id']}")

    analyzer = TrivyAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        run_id=run_id
    )

    logger.info(f"[Vulnerabilities] Completed Trivy analysis for repository: {repo['repo_id']}")


sub_tasks = [
    run_trivy_analysis_task
]


vulnerabilities_flow = create_analysis_flow(
    flow_name="vulnerabilities_flow",
    flow_run_name=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    default_sub_tasks=sub_tasks,
    default_sub_dir="vulnerabilities",
    default_flow_prefix="VULN",
    default_batch_size=1000,
    default_concurrency=10
)


if __name__ == "__main__":
    vulnerabilities_flow({
        "payload": {
            "host_name": [Config.GITLAB_HOSTNAME],
            "main_language": ["Java"]
        }
    })
