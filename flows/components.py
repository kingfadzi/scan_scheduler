import asyncio
from datetime import datetime
from prefect import flow, task, get_run_logger
from prefect.cache_policies import NO_CACHE
from modular.analyzer.dependency_analysis import DependencyAnalyzer
from modular.analyzer.kantra_analysis import KantraAnalyzer
from modular.shared.models import Session

from modular.shared.tasks import (
    generic_main_flow,
    generic_single_repo_processing_flow
)
from modular.shared.utils import generate_repo_flow_run_name, generate_main_flow_run_name


@flow(name="Component Patterns Main Flow", flow_run_name=generate_main_flow_run_name)
async def component_patterns_flow(payload: dict):
    await generic_main_flow(
        payload=payload,
        single_repo_processing_flow=component_patterns_repo_processing_flow,
        flow_prefix="Component Patterns",
        batch_size=10
    )


@flow(flow_run_name=generate_repo_flow_run_name)
def component_patterns_repo_processing_flow(repo, repo_slug, run_id):

    sub_tasks = [
        run_dependency_analysis_task,
        run_kantra_analysis_task
    ]

    generic_single_repo_processing_flow(
        repo=repo,
        run_id=run_id,
        sub_tasks=sub_tasks,
        sub_dir="analyze_components",
        flow_prefix="Component Patterns"
    )


@task(name="Run Dependency Analysis Task", cache_policy=NO_CACHE)
def run_dependency_analysis_task(repo_dir, repo, session, run_id):
    logger = get_run_logger()
    logger.info(f"[Component Patterns] Starting Dependency analysis for repository: {repo.repo_id}")
    analyzer = DependencyAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        session=session,
        run_id=run_id
    )
    logger.info(f"[Component Patterns] Completed Dependency analysis for repository: {repo.repo_id}")


@task(name="Run Kantra Analysis Task", cache_policy=NO_CACHE)
def run_kantra_analysis_task(repo_dir, repo, session, run_id):
    logger = get_run_logger()
    logger.info(f"[Component Patterns] Starting Kantra analysis for repository: {repo.repo_id}")
    analyzer = KantraAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        session=session,
        run_id=run_id
    )
    logger.info(f"[Component Patterns] Completed Kantra analysis for repository: {repo.repo_id}")


if __name__ == "__main__":
    example_payload = {
        "payload": {
            "host_name": ["github.com"],
            "activity_status": ["ACTIVE"],
            "main_language": ["Python"]
        }
    }
    # Run the asynchronous main flow
    asyncio.run(component_patterns_flow(payload=example_payload))
