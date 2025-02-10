import os
import subprocess
import json
from sqlalchemy.dialects.postgresql import insert

from modular.gradle.gradle_helper import GradleHelper
from modular.maven.maven_helper import MavenHelper
from modular.shared.models import Session, ClocMetric
from modular.shared.execution_decorator import analyze_execution
from modular.shared.base_logger import BaseLogger
import logging

class DependencyAnalyzer(BaseLogger):

    def __init__(self):
        self.logger = self.get_logger("DependencyAnalyzer")
        self.logger.setLevel(logging.DEBUG)

    @analyze_execution(session_factory=Session, stage="Dependency Analysis")
    def run_analysis(self, repo_dir, repo, session, run_id=None):

        self.logger.info(f"Starting Dependency Analysis analysis for repo_id: {repo.repo_id} (repo_slug: {repo.repo_slug}).")

        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        MavenHelper().generate_effective_pom(repo_dir)
        GradleHelper().generate_resolved_dependencies(repo_dir)
        # add Python helper
        # add Go helper
        # add JS helper

        return None


if __name__ == "__main__":
    repo_slug = "VulnerableLightApp"
    repo_id = "VulnerableLightApp"
    repo_dir = f"/tmp/{repo_slug}"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug

    repo = MockRepo(repo_id, repo_slug)
    session = Session()

    analyzer = ClocAnalyzer()

    try:
        analyzer.logger.info(f"Starting standalone CLOC analysis for mock repo_id: {repo.repo_id}")
        result = analyzer.run_analysis(repo_dir, repo=repo, session=session, run_id="STANDALONE_RUN_001")
        analyzer.logger.info(f"Standalone CLOC analysis result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone CLOC analysis: {e}")
    finally:
        session.close()
        analyzer.logger.info(f"Database session closed for repo_id: {repo.repo_id}")
