import os
import re
import xml.etree.ElementTree as ET
import json
from sqlalchemy.dialects.postgresql import insert
from modular.shared.models import Session, BuildTool  # Unified model for build tools
from modular.shared.execution_decorator import analyze_execution
from config.config import Config
from modular.shared.base_logger import BaseLogger
import logging
from modular.shared.utils import detect_repo_languages, detect_java_build_tool

class MavenAnalyzer(BaseLogger):
    def __init__(self, logger=None):
        if logger is None:
            self.logger = self.get_logger("MavenAnalyzer")
        else:
            self.logger = logger
        self.logger.setLevel(logging.DEBUG)

    @analyze_execution(session_factory=Session, stage="Maven Build Analysis")
    def run_analysis(self, repo_dir, repo, session, run_id=None):
        self.logger.info(f"Starting Maven build analysis for repo_id: {repo.repo_id} (repo slug: {repo.repo_slug}).")


        repo_languages = detect_repo_languages(repo.repo_id, session)
        if 'Java' not in repo_languages:
            message = f"Repo {repo.repo_id} is not a Java project. Skipping."
            self.logger.info(message)
            return message

        java_build_tool = detect_java_build_tool(repo_dir)
        if java_build_tool != 'Maven':
            message = f"Repo {repo.repo_id} is Java but doesn't use Maven. Skipping."
            self.logger.info(message)
            return message

        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.info(error_message)
            raise FileNotFoundError(error_message)

        pom_path = os.path.join(repo_dir, "pom.xml")
        if not os.path.exists(pom_path):
            message = f"pom.xml not found in repository directory: {repo_dir}. Not a Maven project."
            self.logger.info(message)
            return message

        java_version = "Unknown"
        try:
            tree = ET.parse(pom_path)
            root = tree.getroot()
            ns = {'m': 'http://maven.apache.org/POM/4.0.0'}
            properties = root.find("m:properties", ns)
            if properties is not None:
                java_elem = properties.find("m:maven.compiler.source", ns)
                if java_elem is None:
                    java_elem = properties.find("m:java.version", ns)
                if java_elem is not None and java_elem.text:
                    java_version = java_elem.text.strip()
        except Exception as e:
            self.logger.error(f"Error parsing pom.xml: {e}")

        maven_version = "Not determined from pom.xml"

        self.logger.info(f"Detected Maven build tool. Maven version: {maven_version}, Java version: {java_version}")

        try:
            session.execute(
                insert(BuildTool).values(
                    repo_id=repo.repo_id,
                    tool="Maven",
                    tool_version=maven_version,
                    runtime_version=java_version,
                ).on_conflict_do_update(
                    index_elements=["repo_id", "tool"],
                    set_={
                        "tool_version": maven_version,
                        "runtime_version": java_version,
                    }
                )
            )
            session.commit()
            self.logger.info(f"Maven build analysis results successfully committed for repo_id: {repo.repo_id}.")
        except Exception as e:
            self.logger.exception(f"Error persisting Maven build analysis results for repo_id {repo.repo_id}: {e}")
            raise RuntimeError(e)

        result = {
            "repo_id": repo.repo_id,
            "tool": "Maven",
            "tool_version": maven_version,
            "runtime_version": java_version,
        }
        self.logger.info("Maven build analysis completed.")
        return json.dumps(result)


if __name__ == "__main__":

    repo_dir = "/tmp/WebGoat"

    repo_slug = "WebGoats"
    repo_id = "WebGoat"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug
            self.repo_name = repo_slug

    repo = MockRepo("sonar-metrics", "sonar-metrics")
    session = Session()
    analyzer = MavenAnalyzer()
    try:
        result = analyzer.run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id="STANDALONE_RUN")
        analyzer.logger.info(f"Standalone Maven build analysis result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone Maven build analysis: {e}")
    finally:
        session.close()
