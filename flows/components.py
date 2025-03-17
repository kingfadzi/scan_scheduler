import asyncio
from prefect import flow, task, get_run_logger
from prefect.cache_policies import NO_CACHE
from modular.analyzer.dependency_analysis import DependencyAnalyzer
from modular.analyzer.kantra_analysis import KantraAnalyzer
from modular.analyzer.grype_analysis import GrypeAnalyzer
from modular.analyzer.xeol_analysis import XeolAnalyzer
from modular.analyzer.syft_analysis import SyftAnalyzer
from modular.analyzer.maven_analysis import MavenAnalyzer
from modular.analyzer.gradle_jdk_mapper import GradlejdkAnalyzer
from modular.analyzer.category_analysis import CategoryAnalyzer
from config.config import Config
from modular.shared.utils import Utils
from flows.tasks import (
    generic_main_flow,
    generic_single_repo_processing_flow
)


@flow(flow_run_name=Utils.generate_main_flow_run_name)
async def component_patterns_flow(payload: dict):
    await generic_main_flow(
        payload=payload,
        single_repo_processing_flow=component_patterns_repo_processing_flow,
        flow_prefix="Component Patterns",
        batch_size=1000,
        concurrency_limit=10
    )


@flow(flow_run_name=Utils.generate_repo_flow_run_name)
def component_patterns_repo_processing_flow(repo, repo_slug, run_id):

    sub_tasks = [
        run_dependency_analysis_task,
        run_maven_analysis_task,
        run_gradle_analysis_task,
        run_syft_analysis_task,
        run_grype_analysis_task,
        run_xeol_analysis_task,
    ]

    generic_single_repo_processing_flow(
        repo=repo,
        run_id=run_id,
        sub_tasks=sub_tasks,
        sub_dir="analyze_components",
        flow_prefix="Component Patterns"
    )

@task(name="Syft Analysis Task", cache_policy=NO_CACHE)
def run_syft_analysis_task(repo_dir, repo, session, run_id):
    logger = get_run_logger()
    logger.info(f"[Component Patterns] Starting Syft analysis for repository: {repo.repo_id}")
    analyzer = SyftAnalyzer(logger=logger)
    result = analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        session=session,
        run_id=run_id
    )
    logger.info(f"[Component Patterns] Completed Syft analysis for repository: {repo.repo_id}")



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


@task(name="Run Grype Analysis Task", cache_policy=NO_CACHE)
def run_grype_analysis_task(repo_dir, repo, session, run_id):
    logger = get_run_logger()
    logger.info(f"[Component Patterns] Starting Grype analysis for repository: {repo.repo_id}")
    analyzer = GrypeAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        session=session,
        run_id=run_id
    )
    logger.info(f"[Component Patterns] Completed Grype analysis for repository: {repo.repo_id}")


@task(name="Run Xeol Analysis Task", cache_policy=NO_CACHE)
def run_xeol_analysis_task(repo_dir, repo, session, run_id):
    logger = get_run_logger()
    logger.info(f"[Component Patterns] Starting Xeol analysis for repository: {repo.repo_id}")
    analyzer = XeolAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        session=session,
        run_id=run_id
    )
    logger.info(f"[Component Patterns] Completed Xeol analysis for repository: {repo.repo_id}")


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


@task(name="Run Maven Analysis Task", cache_policy=NO_CACHE)
def run_maven_analysis_task(repo_dir, repo, session, run_id):
    logger = get_run_logger()
    logger.info(f"[Component Patterns] Starting Maven analysis for repository: {repo.repo_id}")
    analyzer = MavenAnalyzer(logger=logger)
    result = analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        session=session,
        run_id=run_id
    )
    logger.info(f"[Component Patterns] Completed Maven analysis for repository: {repo.repo_id}")
    return result


@task(name="Run Gradle Analysis Task", cache_policy=NO_CACHE)
def run_gradle_analysis_task(repo_dir, repo, session, run_id):
    logger = get_run_logger()
    logger.info(f"[Component Patterns] Starting Gradle analysis for repository: {repo.repo_id}")
    analyzer = GradlejdkAnalyzer(logger=logger)
    result = analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        session=session,
        run_id=run_id
    )
    logger.info(f"[Component Patterns] Completed Gradle analysis for repository: {repo.repo_id}")
    return result


@task(name="Category Analysis Task", cache_policy=NO_CACHE)
def run_catgeory_analysis_task(session, run_id):
    logger = get_run_logger()
    logger.info(f"[Component Patterns] Starting Category analysis")
    analyzer = CategoryAnalyzer(logger=logger)
    analyzer.run_analysis()
    logger.info(f"[Component Patterns] Completed Category analysis.")


if __name__ == "__main__":
    example_payload = {
        "payload": {
            "host_name": [Config.GITLAB_HOSTNAME],
           # "activity_status": ["ACTIVE"],
           # "main_language": ["Java"]
        }
    }
    # Run the asynchronous main flow
    asyncio.run(component_patterns_flow(payload=example_payload))

