import os
import logging
from sqlalchemy.dialects.postgresql import insert
from modular.shared.models import Session, BuildTool  # Unified model for build tools
from modular.shared.execution_decorator import analyze_execution
from modular.shared.utils import Utils
from modular.gradle.environment_manager import GradleEnvironmentManager
from modular.shared.base_logger import BaseLogger


class GradleAnalyzer(BaseLogger):
    def __init__(self, logger=None):
        if logger is None:
            self.logger = self.get_logger("GradleAnalyzer")
        else:
            self.logger = logger
        self.logger.setLevel(logging.DEBUG)
        self.utils = Utils(logger=logger)

    @analyze_execution(session_factory=Session, stage="Gradle Build Analysis")
    def run_analysis(self, repo_dir, repo, session, run_id=None):
        self.logger.info(f"Starting Gradle build analysis for repo_id: {repo.repo_id} (repo slug: {repo.repo_slug}).")

        repo_languages = self.utils.detect_repo_languages(repo.repo_id, session)
        if 'Java' not in repo_languages:
            message = f"Repo {repo.repo_id} is not a Java project. Skipping."
            self.logger.info(message)
            return message

        # Check if build tool is Gradle
        java_build_tool = self.utils.detect_java_build_tool(repo_dir)
        if java_build_tool != 'Gradle':
            message = f"Repo {repo.repo_id} is Java but doesn't use Gradle. Skipping."
            self.logger.info(message)
            return message

        env_manager = GradleEnvironmentManager(logger=self.logger)
        gradle_versions = env_manager.get_java_and_gradle_versions(repo_dir=repo_dir)

        if not gradle_versions:
            message = f"Failed to determine Java and Gradle versions for repo '{repo.repo_id}'."
            self.logger.error(message)
            return message

        gradle_version = gradle_versions.get("gradle_version", "Unknown")
        java_version = gradle_versions.get("java_version", "unknown")

        self.logger.info(f"Detected Gradle build tool. Gradle version: {gradle_version}, Java version: {java_version}")

        try:
            session.execute(
                insert(BuildTool).values(
                    repo_id=repo.repo_id,
                    tool="Gradle",
                    tool_version=gradle_version,
                    runtime_version=java_version,
                ).on_conflict_do_update(
                    index_elements=["repo_id", "tool"],
                    set_={
                        "tool_version": gradle_version,
                        "runtime_version": java_version,
                    }
                )
            )
            session.commit()
            self.logger.info(f"Gradle build analysis results successfully committed for repo_id: {repo.repo_id}.")
        except Exception as e:
            self.logger.exception(f"Error persisting Gradle build analysis results for repo_id {repo.repo_id}: {e}")
            raise RuntimeError(e)

        result = f"Repo ID: {repo.repo_id}, Tool: Gradle, Gradle Version: {gradle_version}, Java Version: {java_version}"
        self.logger.info("Gradle build analysis completed.")
        return result


if __name__ == "__main__":
    repo_dir = "/tmp/VulnerableApp"
    repo_id = "vulnerable-apps/VulnerableApp"
    repo_slug = "VulnerableApp"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug
            self.repo_name = repo_slug

    repo = MockRepo(repo_id, repo_slug)
    session = Session()
    analyzer = GradleAnalyzer()

    try:
        result = analyzer.run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id="STANDALONE_RUN")
        analyzer.logger.info(f"Standalone Gradle build analysis result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone Gradle build analysis: {e}")
    finally:
        session.close()
