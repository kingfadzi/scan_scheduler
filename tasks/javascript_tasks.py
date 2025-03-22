from prefect import task, get_run_logger
from prefect.cache_policies import NO_CACHE

from plugins.javascript.javascript_dependencies import JavaScriptDependencyAnalyzer
from plugins.javascript.javascript_tools import JavaScriptBuildToolAnalyzer


@task(name="Run JavaScript Dependency Analysis Task", cache_policy=NO_CACHE)
def run_javascript_dependency_task(repo_dir, repo):
    logger = get_run_logger()
    logger.info(f"Starting JavaScript Dependency analysis for repository: {repo['repo_id']}")
    analyzer = JavaScriptDependencyAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo
    )
    logger.info(f"Completed JavaScript Dependency analysis for repository: {repo['repo_id']}")


@task(name="Run JavaScript Build Tool Analysis Task", cache_policy=NO_CACHE)
def run_javascript_build_tool_task(repo_dir, repo):
    logger = get_run_logger()
    logger.info(f"Starting JavaScript Build Tool analysis for repository: {repo['repo_id']}")
    analyzer = JavaScriptBuildToolAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo
    )
    logger.info(f"Completed JavaScript Build Tool analysis for repository: {repo['repo_id']}")
