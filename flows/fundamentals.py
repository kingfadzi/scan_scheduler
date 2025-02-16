import asyncio
import logging
from prefect import flow, task, get_run_logger
from prefect.cache_policies import NO_CACHE

from modular.analyzer.gitlog_analysis import GitLogAnalyzer
from modular.analyzer.go_enry_analysis import GoEnryAnalyzer
from modular.analyzer.lizard_analysis import LizardAnalyzer
from modular.analyzer.cloc_analysis import ClocAnalyzer

from modular.shared.models import Session, Repository
from modular.shared.tasks import (
    generic_main_flow,
    generic_single_repo_processing_flow,
    generate_repo_flow_run_name,
    generate_main_flow_run_name
)

@flow(name="Fundamental Metrics Main Flow", flow_run_name=generate_main_flow_run_name)
async def fundamental_metrics_flow(payload: dict):
    await generic_main_flow(
        payload=payload,
        single_repo_processing_flow=fundamental_metrics_repo_processing_flow,
        flow_prefix="Fundamental Metrics",
        batch_size=1000,
        num_partitions=10,
    )

@flow(flow_run_name=generate_repo_flow_run_name)
def fundamental_metrics_repo_processing_flow(repo, repo_slug, run_id):
    sub_tasks = [
        run_lizard_task,
        run_cloc_task,
        run_goenry_task,
        run_gitlog_task
    ]
    
    generic_single_repo_processing_flow(
        repo=repo,
        run_id=run_id,
        sub_tasks=sub_tasks,
        sub_dir="analyze_fundamentals",
        flow_prefix="Fundamental Metrics"
    )

@task(name="Run Lizard Analysis Task", cache_policy=NO_CACHE)
def run_lizard_task(repo_dir, repo, session, run_id):
    logger = get_run_logger()
    logger.info(f"[Fundamental Metrics] Starting Lizard analysis for repository: {repo.repo_id}")
    analyzer = LizardAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        session=session,
        run_id=run_id
    )
    logger.info(f"[Fundamental Metrics] Completed Lizard analysis for repository: {repo.repo_id}")

@task(name="Run CLOC Analysis Task", cache_policy=NO_CACHE)
def run_cloc_task(repo_dir, repo, session, run_id):
    logger = get_run_logger()
    logger.info(f"[Fundamental Metrics] Starting CLOC analysis for repository: {repo.repo_id}")
    analyzer = ClocAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        session=session,
        run_id=run_id
    )
    logger.info(f"[Fundamental Metrics] Completed CLOC analysis for repository: {repo.repo_id}")

@task(name="Run GoEnry Analysis Task", cache_policy=NO_CACHE)
def run_goenry_task(repo_dir, repo, session, run_id):
    logger = get_run_logger()
    logger.info(f"[Fundamental Metrics] Starting GoEnry analysis for repository: {repo.repo_id}")
    analyzer = GoEnryAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        session=session,
        run_id=run_id
    )
    logger.info(f"[Fundamental Metrics] Completed GoEnry analysis for repository: {repo.repo_id}")

@task(name="Run GitLog Analysis Task", cache_policy=NO_CACHE)
def run_gitlog_task(repo_dir, repo, session, run_id):
    logger = get_run_logger()
    logger.info(f"[Fundamental Metrics] Starting GitLog analysis for repository: {repo.repo_id}")
    analyzer = GitLogAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        session=session,
        run_id=run_id
    )
    logger.info(f"[Fundamental Metrics] Completed GitLog analysis for repository: {repo.repo_id}")

if __name__ == "__main__":
    example_payload = {
        "payload": {
            "host_name": ["github.com"],
            "activity_status": ["ACTIVE"],
            "main_language": ["Python"]
        }
    }
    asyncio.run(fundamental_metrics_flow(payload=example_payload))