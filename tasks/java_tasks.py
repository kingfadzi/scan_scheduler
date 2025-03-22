from prefect import task, get_run_logger
from prefect.cache_policies import NO_CACHE

from plugins.java.gradle.gradle_dependencies import GradleDependencyAnalyzer
from plugins.java.gradle.gradle_jdk import GradlejdkAnalyzer
from plugins.java.maven.maven_dependencies import MavenDependencyAnalyzer
from plugins.java.maven.maven_jdk import MavenJdkAnalyzer


@task(name="Run Gradle Dependency Analysis Task", cache_policy=NO_CACHE)
def run_gradle_dependency_task(repo_dir, repo):
    logger = get_run_logger()
    logger.info(f"Starting Gradle Dependency analysis for repository: {repo['repo_id']}")
    analyzer = GradleDependencyAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo
    )
    logger.info(f"Completed Gradle Dependency analysis for repository: {repo['repo_id']}")


@task(name="Run Gradle JDK Analysis Task", cache_policy=NO_CACHE)
def run_gradlejdk_task(repo_dir, repo):
    logger = get_run_logger()
    logger.info(f"Starting Gradle JDK analysis for repository: {repo['repo_id']}")
    analyzer = GradlejdkAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo
    )
    logger.info(f"Completed Gradle JDK analysis for repository: {repo['repo_id']}")


@task(name="Run Maven Dependency Analysis Task", cache_policy=NO_CACHE)
def run_maven_dependency_task(repo_dir, repo):
    logger = get_run_logger()
    logger.info(f"Starting Maven Dependency analysis for repository: {repo['repo_id']}")
    analyzer = MavenDependencyAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo
    )
    logger.info(f"Completed Maven Dependency analysis for repository: {repo['repo_id']}")


@task(name="Run Maven JDK Analysis Task", cache_policy=NO_CACHE)
def run_mavenjdk_task(repo_dir, repo):
    logger = get_run_logger()
    logger.info(f"Starting Maven JDK analysis for repository: {repo['repo_id']}")
    analyzer = MavenJdkAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo
    )
    logger.info(f"Completed Maven JDK analysis for repository: {repo['repo_id']}")
