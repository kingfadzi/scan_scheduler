import json
import os
import logging
from modular.shared.models import Session, Dependency, Repository, GoEnryAnalysis
from modular.shared.execution_decorator import analyze_execution
from modular.shared.base_logger import BaseLogger
from modular.python.python_helper import PythonHelper
from modular.javascript.javascript_helper import JavaScriptHelper
from modular.go.go_helper import GoHelper
from modular.maven.maven_helper import MavenHelper
from modular.gradle.gradle_helper import GradleHelper
from sqlalchemy.dialects.postgresql import insert
from modular.shared.utils import detect_repo_languages, detect_java_build_tool

class DependencyAnalyzer(BaseLogger):

    def __init__(self, logger=None):
        if logger is None:
            self.logger = self.get_logger("DependencyAnalyzer")
        else:
            self.logger = logger
        self.logger.setLevel(logging.DEBUG)

        self.python_helper = PythonHelper(logger=logger)
        self.js_helper = JavaScriptHelper(logger=logger)
        self.go_helper = GoHelper(logger=logger)
        self.maven_helper = MavenHelper(logger=logger)
        self.gradle_helper = GradleHelper(logger=logger)

    @analyze_execution(session_factory=Session, stage="Dependency Analysis")
    def run_analysis(self, repo_dir, repo, session, run_id=None):
        self.logger.info(f"Starting dependency analysis for repo_id: {repo.repo_id} (repo_slug: {repo.repo_slug}).")

        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        repo_languages = detect_repo_languages(repo.repo_id, session)
        if not repo_languages:
            self.logger.warning(f"No detected languages for repo_id: {repo.repo_id}. Skipping dependency analysis.")
            return f"skipped: No detected languages for repo {repo.repo_id}."

        dependencies = []

        try:
            if "Python" in repo_languages:
                self.logger.info(f"Detected Python in repo_id: {repo.repo_id}. Running Python dependency analysis.")
                dependencies.extend(self.python_helper.process_repo(repo_dir, repo))

            if "JavaScript" in repo_languages or "TypeScript" in repo_languages:
                self.logger.info(f"Detected JavaScript/TypeScript in repo_id: {repo.repo_id}. Running JavaScript dependency analysis.")
                dependencies.extend(self.js_helper.process_repo(repo_dir, repo))

            if "Go" in repo_languages:
                self.logger.info(f"Detected Go in repo_id: {repo.repo_id}. Running Go dependency analysis.")
                dependencies.extend(self.go_helper.process_repo(repo_dir, repo))

            if "Java" in repo_languages:
                self.logger.info(f"Detected Java in repo_id: {repo.repo_id}. Identifying build system.")
                build_tool = detect_java_build_tool(repo_dir)
                if build_tool == "Maven":
                    self.logger.info(f"Processing Maven project in {repo_dir}")
                    dependencies.extend(self.maven_helper.process_repo(repo_dir, repo))
                elif build_tool == "Gradle":
                    self.logger.info(f"Processing Gradle project in {repo_dir}")
                    dependencies.extend(self.gradle_helper.process_repo(repo_dir, repo))
                else:
                    self.logger.warning("No supported Java build system detected.")

            self.persist_dependencies(dependencies, session)

            #return f"Dependencies: {dependencies}"
            return f"Dependencies: {len(dependencies)}"


        except Exception as e:
            self.logger.error(f"Error during dependency analysis: {e}")
            raise

        except FileNotFoundError as e:
            self.logger.error(str(e))
            return f"error: {str(e)}"
        except Exception as e:
            self.logger.exception(f"Error during dependency analysis for repo_id {repo.repo_id}: {e}")
            return f"error: {str(e)}"


    def persist_dependencies(self, dependencies, session):
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

            session.execute(upsert_stmt, dep_dicts)
            session.commit()
            self.logger.info("Dependency insertion successful.")

        except Exception as e:
            session.rollback()
            self.logger.error(f"Failed to insert dependencies: {e}")
            raise


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
    repo_dir = "/tmp/VulnerableApp"
    session = Session()

    try:
        analyzer.logger.info(f"Starting analysis for {repo.repo_slug}")
        result = analyzer.run_analysis(repo_dir, repo=repo, session=session, run_id="STANDALONE_RUN_001")
        analyzer.logger.info(f"Analysis completed successfully")
    except Exception as e:
        analyzer.logger.error(f"Analysis failed: {e}")
    finally:
        session.close()
        analyzer.logger.info("Database session closed")
