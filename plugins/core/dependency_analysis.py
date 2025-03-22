import os
import logging
from shared.models import Session, Dependency
from shared.execution_decorator import analyze_execution
from shared.base_logger import BaseLogger
from plugins.python.python_dependencies import PythonDependencyAnalyzer
from plugins.javascript.javascript_dependencies import JavaScriptDependencyAnalyzer
from plugins.go.go_dependencies import GoHelper
from plugins.java.maven.maven_dependencies import MavenDependencyAnalyzer
from plugins.java.gradle.gradle_dependencies import GradleDependencyAnalyzer
from sqlalchemy.dialects.postgresql import insert
from shared.utils import Utils

class DependencyAnalyzer(BaseLogger):

    def __init__(self, logger=None):
        if logger is None:
            self.logger = self.get_logger("DependencyAnalyzer")
        else:
            self.logger = logger
        self.logger.setLevel(logging.DEBUG)

        self.python_da = PythonDependencyAnalyzer(logger=logger)
        self.js_da = JavaScriptDependencyAnalyzer(logger=logger)
        self.go_da = GoHelper(logger=logger)
        self.maven_da = MavenDependencyAnalyzer(logger=logger)
        self.gradle_da = GradleDependencyAnalyzer(logger=logger)
        self.utils = Utils(logger=logger)

    @analyze_execution(session_factory=Session, stage="Dependency Analysis")
    def run_analysis(self, repo_dir, repo, run_id=None):
        self.logger.info(f"Starting dependency analysis for repo_id: {repo['repo_id']} (repo_slug: {repo['repo_slug']}).")

        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        main_language = self.utils.get_repo_main_language(repo['repo_id'])
        if not main_language:
            self.logger.warning(f"No main language detected for repo_id: {repo['repo_id']}. Skipping dependency analysis.")
            return f"skipped: No main language detected for repo {repo['repo_id']}."

        dependencies = []

        try:
            if main_language == "Python":
                self.logger.info(f"Main language is Python for repo_id: {repo['repo_id']}. Running dependency analysis.")
                dependencies.extend(self.python_da.process_repo(repo_dir, repo))

            elif main_language in ["JavaScript", "TypeScript"]:
                self.logger.info(f"Main language is {main_language} for repo_id: {repo['repo_id']}. Running analysis.")
                dependencies.extend(self.js_da.process_repo(repo_dir, repo))

            elif main_language == "Go":
                self.logger.info(f"Main language is Go for repo_id: {repo['repo_id']}. Running analysis.")
                dependencies.extend(self.go_da.process_repo(repo_dir, repo))

            elif main_language == "Java":
                self.logger.info(f"Main language is Java for repo_id: {repo['repo_id']}. Identifying build system.")
                build_tool = self.utils.detect_java_build_tool(repo_dir)
                if build_tool == "Maven":
                    dependencies.extend(self.maven_da.process_repo(repo_dir, repo))
                elif build_tool == "Gradle":
                    dependencies.extend(self.gradle_da.process_repo(repo_dir=repo_dir, repo=repo))

            self.persist_dependencies(dependencies)
            return f"Dependencies: {len(dependencies)}"

        except Exception as e:
            self.logger.error(f"Error processing {main_language} dependencies: {str(e)}")
            return f"error: {str(e)}"



    def persist_dependencies(self, dependencies):
        if not dependencies:
            self.logger.info("No dependencies to persist.")
            return

        try:
            self.logger.info(f"Inserting {len(dependencies)} dependencies into the database.")

            dep_dicts = [
                {
                    "repo_id": dep.repo_id,
                    "name": dep.name,
                    "version": dep.version,
                    "package_type": dep.package_type,
                }
                for dep in dependencies
            ]

            ins_stmt = insert(Dependency)

            upsert_stmt = ins_stmt.on_conflict_do_nothing(
                index_elements=['repo_id', 'name', 'version']
            )

            session = Session()
            session.execute(upsert_stmt, dep_dicts)
            session.commit()
            self.logger.info("Dependency insertion successful.")

        except Exception as e:
            session.rollback()
            self.logger.error(f"Failed to insert dependencies: {e}")
            raise
        finally:
            session.close()


if __name__ == "__main__":
    repo_slug = "VulnerableApp"
    repo_id = "vulnerable-apps/VulnerableApp"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug
            self.repo_name = repo_slug

    analyzer = DependencyAnalyzer()
    repo = MockRepo(repo_id, repo_slug)
    repo_dir = "/tmp/gradle-example"
    session = Session()

    try:
        analyzer.logger.info(f"Starting analysis for {repo['repo_slug']}")
        result = analyzer.run_analysis(repo_dir, repo=repo, session=session, run_id="STANDALONE_RUN_001")
        analyzer.logger.info(f"Analysis completed successfully")
    except Exception as e:
        analyzer.logger.error(f"Analysis failed: {e}")
    finally:
        session.close()
        analyzer.logger.info("Database session closed")
