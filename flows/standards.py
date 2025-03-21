from prefect import task, get_run_logger
from prefect.cache_policies import NO_CACHE
from config.config import Config
from plugins.common.checkov_analysis import CheckovAnalyzer
from plugins.common.semgrep_analysis import SemgrepAnalyzer
from flows.factory import create_analysis_flow
from datetime import datetime


@task(name="Run Checkov Analysis Task", cache_policy=NO_CACHE)
def run_checkov_analysis_task(repo_dir, repo, run_id):

    logger = get_run_logger()
    logger.info(f"[Standards Assessment] Starting Checkov analysis for repository: {repo['repo_id']}")

    analyzer = CheckovAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        run_id=run_id
    )

    logger.info(f"[Standards Assessment] Completed Checkov analysis for repository: {repo['repo_id']}")


@task(name="Run Semgrep Analysis Task", cache_policy=NO_CACHE)
def run_semgrep_analysis_task(repo_dir, repo, run_id):

    logger = get_run_logger()
    logger.info(f"[Standards Assessment] Starting Semgrep analysis for repository: {repo['repo_id']}")

    analyzer = SemgrepAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        run_id=run_id
    )

    logger.info(f"[Standards Assessment] Completed Semgrep analysis for repository: {repo['repo_id']}")


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
    default_batch_size=1000,
    default_concurrency=10
)


if __name__ == "__main__":
    standards_assessment_flow({
        "payload": {
            "host_name": [Config.GITLAB_HOSTNAME],
            "main_language": ["Java"]
        }
    })
