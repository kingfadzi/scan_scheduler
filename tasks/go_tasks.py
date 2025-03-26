from prefect import task, get_run_logger
from prefect.cache_policies import NO_CACHE

from plugins.go.go_dependencies import GoDependencyAnalyzer
from plugins.go.go_tools import GoBuildToolAnalyzer


@task(name="Run Go Dependency Analysis Task", cache_policy=NO_CACHE)
def run_go_dependency_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    logger.info(f"Starting Go Dependency analysis for repository: {repo['repo_id']}")
    analyzer = GoDependencyAnalyzer(logger=logger, run_id=run_id)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo
    )
    logger.info(f"[Fundamental Metrics] Completed Go Dependency analysis for repository: {repo['repo_id']}")


@task(name="Run Go Build Tool Analysis Task", cache_policy=NO_CACHE)
async def run_go_build_tool_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    logger.info(f"Starting Go Build Tool analysis for repository: {repo['repo_id']}")
    analyzer = GoBuildToolAnalyzer(logger=logger, run_id=run_id)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo
    )
    logger.info(f"[Fundamental Metrics] Completed Go Build Tool analysis for repository: {repo['repo_id']}")
