import subprocess
import os
import json
from modular.shared.execution_decorator import analyze_execution
from config.config import Config
from modular.shared.models import Session
from modular.shared.base_logger import BaseLogger
import logging

class SyftAnalyzer(BaseLogger):
    def __init__(self, repo_id, repo_slug, logger=None):
        if logger is None:
            self.logger = self.get_logger("SyftAnalyzer")
        else:
            self.logger = logger
        self.logger.setLevel(logging.DEBUG)
        self.repo_id = repo_id
        self.repo_slug = repo_slug

    @analyze_execution(session_factory=Session, stage="Syft Analysis")
    def run_analysis(self, repo_dir, repo, session, run_id=None):
        self.logger.info(f"Starting Syft analysis for repo_id: {self.repo_id} (repo slug: {repo.repo_slug}).")
        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        sbom_file_path = os.path.join(repo_dir, "sbom.json")
        self.logger.info(f"Generating SBOM for repo_id: {self.repo_id} using Syft.")

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
            error_message = f"Syft command timed out for repo_id {self.repo_id} after {e.timeout} seconds."
            self.logger.error(error_message)
            raise RuntimeError(error_message)
        except subprocess.CalledProcessError as e:
            error_message = f"Syft command failed for repo_id {self.repo_id}: {e.stderr.strip()}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        if os.path.exists(sbom_file_path):
            self.logger.info(f"SBOM file created at: {sbom_file_path}")
        else:
            self.logger.warning(f"SBOM file not found at expected path: {sbom_file_path}")

        with open(sbom_file_path, "r") as f:
            sbom_json = json.load(f)

        self.logger.info("Syft analysis completed.")
        return json.dumps(sbom_json)

if __name__ == '__main__':
    # Set the variables separately so they can be easily replaced for testing.
    repo_id = "sonar-metrics"
    repo_slug = "sonar-metrics"
    repo_dir = "/tmp/sonar-metrics"  # Adjust this path as needed

    # Create a simple mock repo object
    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug

    repo = MockRepo(repo_id, repo_slug)
    analyzer = SyftAnalyzer(repo_id, repo_slug)
    session = Session()

    try:
        result = analyzer.run_analysis(repo_dir, repo=repo, session=session, run_id="STANDALONE_RUN_001")
        analyzer.logger.info("Stand-alone Syft analysis result:\n%s", result)
    except Exception as e:
        analyzer.logger.error("Error during Syft analysis: %s", e)
    finally:
        session.close()