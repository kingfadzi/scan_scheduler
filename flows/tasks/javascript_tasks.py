from prefect import task, get_run_logger
from prefect.cache_policies import NO_CACHE
from plugins.javascript.javascript_dependencies import JavaScriptDependencyAnalyzer
from plugins.build_tools.javascript_tools import JavaScriptBuildToolAnalyzer


@task(name="Run JavaScript Dependency Analysis Task", cache_policy=NO_CACHE)
async def run_javascript_dependency_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    try:
        logger.info(f"Starting JavaScript Dependency analysis for repository: {repo['repo_id']}")
        analyzer = JavaScriptDependencyAnalyzer(logger=logger, run_id=run_id)
        analyzer.run_analysis(repo_dir=repo_dir, repo=repo)
        logger.info(f"Completed JavaScript Dependency analysis for repository: {repo['repo_id']}")
    except Exception as exc:
        logger.exception("Error during JavaScript Dependency analysis")
        raise exc


@task(name="Run JavaScript Build Tool Analysis Task", cache_policy=NO_CACHE)
async def run_javascript_build_tool_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    try:
        logger.info(f"Starting JavaScript Build Tool analysis for repository: {repo['repo_id']}")
        analyzer = JavaScriptBuildToolAnalyzer(logger=logger, run_id=run_id)
        analyzer.run_analysis(repo_dir=repo_dir, repo=repo)
        logger.info(f"Completed JavaScript Build Tool analysis for repository: {repo['repo_id']}")
    except Exception as exc:
        logger.exception("Error during JavaScript Build Tool analysis")
        raise exc
