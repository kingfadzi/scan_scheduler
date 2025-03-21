from modular.analyzer.cloning import CloningAnalyzer
from modular.shared.utils import Utils
from prefect.cache_policies import NO_CACHE
import asyncio
from prefect import task
from prefect.context import get_run_context
from modular.shared.models import Session
from datetime import datetime
from prefect import flow, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner
from typing import List, Callable


@task(name="Start Task")
def start_task(flow_prefix: str) -> str:
    logger = get_run_logger()
    logger.info(f"[{flow_prefix}] Starting flow")
    return flow_prefix


@task(name="Create Batches Task")
def create_batches_task(payload: dict, batch_size) -> list:
    utils = Utils(logger = get_run_logger())
    partitions = utils.create_batches(payload, batch_size)
    return partitions

@task(name="Fetch Repositories Task")
def fetch_repositories_task(payload: dict, batch_size):
    utils = Utils(logger = get_run_logger())
    all_repos = []
    for batch in utils.fetch_repositories(payload, batch_size=batch_size):
        all_repos.extend(batch)
    return all_repos


@task(name="Clone Repository Task", cache_policy=NO_CACHE)
def clone_repository_task(repo, run_id, sub_dir):
    logger = get_run_logger()
    cloning_analyzer = CloningAnalyzer(logger=logger)
    result = cloning_analyzer.clone_repository(repo=repo, run_id=run_id, sub_dir=sub_dir)
    return result


@task(name="Clean Up Repository Task", cache_policy=NO_CACHE)
def cleanup_repo_task(repo_dir):
    logger = get_run_logger()
    cloning_analyzer = CloningAnalyzer(logger=logger)
    cloning_analyzer.cleanup_repository_directory(repo_dir)


@task(name="Update Processing Status Task", cache_policy=NO_CACHE)
def update_status_task(repo, run_id, session):
    utils = Utils(logger = get_run_logger())
    utils.determine_final_status(repo, run_id, session)


@task(name="Refresh Views Task")
def refresh_views_task(flow_prefix: str) -> None:
    logger = get_run_logger()
    logger.info(f"[{flow_prefix}] Refreshing views")
    utils = Utils(logger = get_run_logger())
    utils.refresh_views()
    logger.info(f"[{flow_prefix}] Views refreshed")


# --------------------------
# Repository Processing Flow
# --------------------------
@flow(
    flow_run_name=Utils.generate_repo_flow_run_name,
    task_runner=ConcurrentTaskRunner(max_workers=10)  # Sequential tasks
)
def generic_single_repo_processing_flow(
        repo,
        run_id: str,
        sub_tasks: List[Callable],
        sub_dir: str,
        flow_prefix: str
):
    """Process one repository with sequential tasks"""
    logger = get_run_logger()

    with Session() as session:
        attached_repo = session.merge(repo)
        repo_dir = None

        try:
            # Clone repository (first task)
            repo_dir = clone_repository_task(attached_repo, run_id, sub_dir)

            # Sequential analysis tasks
            for task_fn in sub_tasks:
                task_fn(repo_dir, attached_repo, session, run_id)

        finally:
            if repo_dir:
                cleanup_repo_task(repo_dir)

# --------------------------
# Main Parallel Processing Flow
# --------------------------
@flow(
    flow_run_name=Utils.generate_main_flow_run_name,
    task_runner=ConcurrentTaskRunner(max_workers=10)  # 10 repos in parallel
)
def generic_main_flow(
        payload: dict,
        flow_prefix: str,
        batch_size: int,
        processing_tasks: List[Callable]
):
    """Process multiple repositories in parallel"""
    logger = get_run_logger()

    # Initialization
    start_task(flow_prefix)

    # Fetch repositories
    repos = fetch_repositories_task(payload, batch_size)
    logger.info(f"[{flow_prefix}] Processing {len(repos)} repositories")

    # Get run context
    run_id = str(get_run_context().flow_run.id)

    # Process repositories in parallel
    for repo in repos:
        generic_single_repo_processing_flow(
            repo=repo,
            run_id=run_id,
            sub_tasks=processing_tasks,
            sub_dir="analysis",
            flow_prefix=flow_prefix
        )

    # Finalization
    refresh_views_task(flow_prefix)


