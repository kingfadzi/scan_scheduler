from datetime import datetime

from prefect import task, get_run_logger
from prefect.cache_policies import NO_CACHE
from flows.factory import create_analysis_flow
from plugins.common.dependency_analysis import DependencyAnalyzer
from plugins.common.grype_analysis import GrypeAnalyzer
from plugins.common.xeol_analysis import XeolAnalyzer
from plugins.common.syft_analysis import SyftAnalyzer
from plugins.java.maven.maven_analysis import MavenAnalyzer
from plugins.java.gradle.gradle_jdk_mapper import GradlejdkAnalyzer
from plugins.common.category_analysis import CategoryAnalyzer
from config.config import Config


@task(name="Syft Analysis Task", cache_policy=NO_CACHE)
def run_syft_analysis_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    logger.info(f"[Component Patterns] Starting Syft analysis for repository: {repo['repo_id']}")
    analyzer = SyftAnalyzer(logger=logger)
    result = analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        run_id=run_id
    )
    logger.info(f"[Component Patterns] Completed Syft analysis for repository: {repo['repo_id']}")


@task(name="Run Dependency Analysis Task", cache_policy=NO_CACHE)
def run_dependency_analysis_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    logger.info(f"[Component Patterns] Starting Dependency analysis for repository: {repo['repo_id']}")
    analyzer = DependencyAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        run_id=run_id
    )
    logger.info(f"[Component Patterns] Completed Dependency analysis for repository: {repo['repo_id']}")


@task(name="Run Grype Analysis Task", cache_policy=NO_CACHE)
def run_grype_analysis_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    logger.info(f"[Component Patterns] Starting Grype analysis for repository: {repo['repo_id']}")
    analyzer = GrypeAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        run_id=run_id
    )
    logger.info(f"[Component Patterns] Completed Grype analysis for repository: {repo['repo_id']}")


@task(name="Run Xeol Analysis Task", cache_policy=NO_CACHE)
def run_xeol_analysis_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    logger.info(f"[Component Patterns] Starting Xeol analysis for repository: {repo['repo_id']}")
    analyzer = XeolAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        run_id=run_id
    )
    logger.info(f"[Component Patterns] Completed Xeol analysis for repository: {repo['repo_id']}")


@task(name="Run Maven Analysis Task", cache_policy=NO_CACHE)
def run_maven_analysis_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    logger.info(f"[Component Patterns] Starting Maven analysis for repository: {repo['repo_id']}")
    analyzer = MavenAnalyzer(logger=logger)
    result = analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        run_id=run_id
    )
    logger.info(f"[Component Patterns] Completed Maven analysis for repository: {repo['repo_id']}")
    return result


@task(name="Run Gradle Analysis Task", cache_policy=NO_CACHE)
def run_gradle_analysis_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    logger.info(f"[Component Patterns] Starting Gradle analysis for repository: {repo['repo_id']}")
    analyzer = GradlejdkAnalyzer(logger=logger)
    result = analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        run_id=run_id
    )
    logger.info(f"[Component Patterns] Completed Gradle analysis for repository: {repo['repo_id']}")
    return result


@task(name="Category Analysis Task", cache_policy=NO_CACHE)
def run_catgeory_analysis_task(run_id):
    logger = get_run_logger()
    logger.info(f"[Component Patterns] Starting Category analysis")
    analyzer = CategoryAnalyzer(logger=logger)
    analyzer.run_analysis()
    logger.info(f"[Component Patterns] Completed Category analysis.")


sub_tasks = [
    run_dependency_analysis_task,
    run_maven_analysis_task,
    run_gradle_analysis_task,
    run_syft_analysis_task,
    run_grype_analysis_task,
    run_xeol_analysis_task,
]

component_patterns_flow = create_analysis_flow(
    flow_name="component_patterns_flow",
    flow_run_name=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    default_sub_tasks=sub_tasks,
    default_sub_dir="component_patterns",
    default_flow_prefix="COMPOSITION",
    default_batch_size=10,
    default_concurrency=5
)


if __name__ == "__main__":
    component_patterns_flow({
        "payload": {
            "host_name": [Config.GITLAB_HOSTNAME],
            "main_language": ["Java"]
        }
    })
