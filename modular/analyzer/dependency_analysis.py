import os
import logging
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from modular.shared.models import Session
from modular.shared.execution_decorator import analyze_execution
from modular.shared.base_logger import BaseLogger
from dependency_helpers.python_helper import PythonHelper
from dependency_helpers.javascript_helper import JavaScriptHelper
from dependency_helpers.go_helper import GoHelper
from dependency_helpers.maven_helper import MavenHelper
from dependency_helpers.gradle_helper import GradleHelper
from modular.shared.models import GoEnryAnalysis

class DependencyAnalyzer(BaseLogger):

    def __init__(self):
        self.logger = self.get_logger("DependencyAnalyzer")
        self.logger.setLevel(logging.DEBUG)
        self.python_helper = PythonHelper()
        self.js_helper = JavaScriptHelper()
        self.go_helper = GoHelper()
        self.maven_helper = MavenHelper()
        self.gradle_helper = GradleHelper()

    @analyze_execution(session_factory=Session, stage="Dependency Analysis")
    def run_analysis(self, repo_dir, repo, session, run_id=None):
        self.logger.info(f"Starting dependency analysis for repo_id: {repo.repo_id} (repo_slug: {repo.repo_slug}).")

        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        repo_languages = self.detect_repo_languages(repo.repo_id, session)

        if not repo_languages:
            self.logger.warning(f"No detected languages for repo_id: {repo.repo_id}. Skipping dependency analysis.")
            return

        try:
            if "Python" in repo_languages:
                self.logger.info(f"Detected Python in repo_id: {repo.repo_id}. Running Python dependency analysis.")
                self.python_helper.process_repo(repo_dir)
            
            if "JavaScript" in repo_languages or "TypeScript" in repo_languages:
                self.logger.info(f"Detected JavaScript/TypeScript in repo_id: {repo.repo_id}. Running JavaScript dependency analysis.")
                self.js_helper.process_repo(repo_dir)
            
            if "Go" in repo_languages:
                self.logger.info(f"Detected Go in repo_id: {repo.repo_id}. Running Go dependency analysis.")
                self.go_helper.process_repo(repo_dir)
            
            if "Java" in repo_languages:
                self.logger.info(f"Detected Java in repo_id: {repo.repo_id}. Identifying build system.")
                build_tool = self.detect_java_build_tool(repo_dir)
                
                if build_tool == "Maven":
                    self.logger.info(f"Processing Maven project in {repo_dir}")
                    self.maven_helper.process_repo(repo_dir)
                elif build_tool == "Gradle":
                    self.logger.info(f"Processing Gradle project in {repo_dir}")
                    self.gradle_helper.process_repo(repo_dir)
                else:
                    self.logger.warning("No supported Java build system detected")

        except Exception as e:
            self.logger.exception(f"Error during dependency analysis for repo_id {repo.repo_id}: {e}")
            raise

    def detect_java_build_tool(self, repo_dir):
        """Determine Java build system by checking for build files"""
        maven_pom = os.path.isfile(os.path.join(repo_dir, "pom.xml"))
        gradle_build = os.path.isfile(os.path.join(repo_dir, "build.gradle"))
        
        if maven_pom and gradle_build:
            self.logger.warning("Both Maven and Gradle build files detected. Prioritizing Maven.")
            return "Maven"
        elif maven_pom:
            self.logger.debug("Maven pom.xml detected")
            return "Maven"
        elif gradle_build:
            self.logger.debug("Gradle build.gradle detected")
            return "Gradle"
        
        self.logger.warning("No Java build system detected (checked for pom.xml and build.gradle)")
        return None

    def detect_repo_languages(self, repo_id, session):
        self.logger.info(f"Querying go_enry_analysis for repo_id: {repo_id}")
        results = session.query(GoEnryAnalysis.language).filter(GoEnryAnalysis.repo_id == repo_id).all()
        languages = {row.language for row in results}

        if languages:
            self.logger.info(f"Detected languages for repo_id {repo_id}: {languages}")
        else:
            self.logger.warning(f"No languages found in go_enry_analysis for repo_id: {repo_id}")

        return languages

if __name__ == "__main__":
    # ... (existing main code remains unchanged)
