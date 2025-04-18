from prefect import task, get_run_logger
from prefect.cache_policies import NO_CACHE
from plugins.python.python_dependencies import PythonDependencyAnalyzer
from plugins.build_tools.python_tools import PythonBuildToolAnalyzer


@task(name="Run Python Dependency Analysis Task", cache_policy=NO_CACHE)
async def run_python_dependency_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    try:
        logger.info(f"Starting Python Dependency analysis for repository: {repo['repo_id']}")
        analyzer = PythonDependencyAnalyzer(logger=logger, run_id=run_id)
        analyzer.run_analysis(repo_dir=repo_dir, repo=repo)
        logger.info(f"Completed Python Dependency analysis for repository: {repo['repo_id']}")
    except Exception as exc:
        logger.exception("Error during Python Dependency analysis")
        raise exc


@task(name="Run Python Build Tool Analysis Task", cache_policy=NO_CACHE)
async def run_python_build_tool_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    try:
        logger.info(f"Starting Python Build Tool analysis for repository: {repo['repo_id']}")
        analyzer = PythonBuildToolAnalyzer(logger=logger, run_id=run_id)
        analyzer.run_analysis(repo_dir=repo_dir, repo=repo)
        logger.info(f"Completed Python Build Tool analysis for repository: {repo['repo_id']}")
    except Exception as exc:
        logger.exception("Error during Python Build Tool analysis")
        raise exc
