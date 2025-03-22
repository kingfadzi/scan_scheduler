from prefect import flow, task, get_run_logger
from prefect.cache_policies import NO_CACHE
from config.config import Config
from datetime import datetime
from plugins.core.gitlog_analysis import GitLogAnalyzer
from plugins.core.go_enry_analysis import GoEnryAnalyzer
from plugins.core.lizard_analysis import LizardAnalyzer
from plugins.core.cloc_analysis import ClocAnalyzer
from flows.factory import create_analysis_flow


@task(name="Run Lizard Analysis Task", cache_policy=NO_CACHE)
def run_lizard_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    logger.info(f"[Fundamental Metrics] Starting Lizard analysis for repository: {repo['repo_id']}")
    analyzer = LizardAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        run_id=run_id
    )
    logger.info(f"[Fundamental Metrics] Completed Lizard analysis for repository: {repo['repo_id']}")


@task(name="Run CLOC Analysis Task", cache_policy=NO_CACHE)
def run_cloc_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    logger.info(f"[Fundamental Metrics] Starting CLOC analysis for repository: {repo['repo_id']}")
    analyzer = ClocAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        run_id=run_id
    )
    logger.info(f"[Fundamental Metrics] Completed CLOC analysis for repository: {repo['repo_id']}")


@task(name="Run GoEnry Analysis Task", cache_policy=NO_CACHE)
def run_goenry_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    logger.info(f"[Fundamental Metrics] Starting GoEnry analysis for repository: {repo['repo_id']}")
    analyzer = GoEnryAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        run_id=run_id
    )
    logger.info(f"[Fundamental Metrics] Completed GoEnry analysis for repository: {repo['repo_id']}")


@task(name="Run GitLog Analysis Task", cache_policy=NO_CACHE)
def run_gitlog_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    logger.info(f"[Fundamental Metrics] Starting GitLog analysis for repository: {repo['repo_id']}")
    analyzer = GitLogAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        run_id=run_id
    )
    logger.info(f"[Fundamental Metrics] Completed GitLog analysis for repository: {repo['repo_id']}")

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
    default_batch_size=1000,
    default_concurrency=10
)


if __name__ == "__main__":
    fundamental_metrics_flow({
        "payload": {
            "host_name": [Config.GITLAB_HOSTNAME],
            "main_language": ["Java"]
        }
    })
