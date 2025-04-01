import subprocess
import os
from shared.execution_decorator import analyze_execution
from config.config import Config
from shared.models import Session
from shared.base_logger import BaseLogger
import logging

class SyftAnalyzer(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)

    #@analyze_execution(session_factory=Session, stage="Syft Analysis")
    def run_analysis(self, repo_dir, repo):
        self.logger.info(f"Starting Syft analysis for repo_id: {repo['repo_id']} (repo slug: {repo['repo_slug']}).")
        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        sbom_file_path = os.path.join(repo_dir, "sbom.json")
        self.logger.info(f"Generating SBOM for repo_id: {repo['repo_id']} using Syft.")

        try:
            command = [
                "syft",
                repo_dir,
                "--output", "json",
                "--file", sbom_file_path
            ]
            self.logger.debug("Executing command: %s", " ".join(command))
            subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                timeout=Config.DEFAULT_PROCESS_TIMEOUT
            )
            self.logger.debug(f"Syft command executed, expecting SBOM at: {sbom_file_path}")
        except subprocess.TimeoutExpired as e:
            error_message = f"Syft command timed out for repo_id {repo['repo_id']} after {e.timeout} seconds."
            self.logger.error(error_message)
            raise RuntimeError(error_message)
        except subprocess.CalledProcessError as e:
            error_message = f"Syft command failed for repo_id {repo['repo_id']}: {e.stderr.strip()}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        if os.path.exists(sbom_file_path):
            message = f"SBOM file created at: {sbom_file_path}"
            self.logger.info(message)
        else:
            message = f"SBOM file not found at expected path: {sbom_file_path}"
            self.logger.warning(message)

        return message

    def generate_sbom(self, repo_dir, repo):
        return self.run_analysis(repo_dir, repo)

if __name__ == "__main__":
    repo_slug = "nosql-injection-vulnapp"
    repo_id = "nosql-injection-vulnapp"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug
            self.repo_name = repo_slug

    analyzer = SyftAnalyzer()
    repo = MockRepo(repo_id, repo_slug)
    repo_dir = f"/tmp/{repo['repo_slug']}"
    session = Session()

    try:
        analyzer.logger.info(f"Starting standalone Syft analysis for repo_id: {repo['repo_id']}")
        result = analyzer.run_analysis(repo_dir, repo=repo)
        analyzer.logger.info(f"Standalone Syft analysis result: {result[:500]}...")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone Syft analysis: {e}")
    finally:
        session.close()
        analyzer.logger.info(f"Database session closed for repo_id: {repo['repo_id']}")
