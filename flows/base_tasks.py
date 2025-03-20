from prefect import flow, task, get_run_logger, unmapped
from prefect.cache_policies import NO_CACHE
from modular.analyzer.cloning import CloningAnalyzer
from modular.shared.utils import Utils


@task(name="Fetch Repositories Task")
def fetch_repositories_task(payload: dict, batch_size):
    logger = get_run_logger()
    utils = Utils(logger = logger)
    all_repos = []
    for batch in utils.fetch_repositories_dict(payload, batch_size=batch_size):
        all_repos.extend(batch)
    logger.info(f"Fetched {len(all_repos)} repositories with payload: {payload}.")
    return all_repos


@task(name="Start Task")
def start_task(flow_prefix: str) -> str:
    logger = get_run_logger()
    logger.info(f"[{flow_prefix}] Starting flow")
    return flow_prefix


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
def update_status_task(repo, run_id):
    utils = Utils(logger = get_run_logger())
    utils.determine_final_status(repo, run_id, session=None)


@task(name="Refresh Views Task")
def refresh_views_task(flow_prefix: str) -> None:
    logger = get_run_logger()
    logger.info(f"[{flow_prefix}] Refreshing views")
    utils = Utils(logger = get_run_logger())
    utils.refresh_views()
    logger.info(f"[{flow_prefix}] Views refreshed")
