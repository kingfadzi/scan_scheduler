import subprocess
import os
from filelock import FileLock
from config.config import Config
from shared.base_logger import BaseLogger
import logging
from pathlib import Path

EXCLUDE_DIRS = {'.gradle', 'build', 'out', 'target', '.git', '.idea', '.settings', 'bin'}

class SBOMProvider(BaseLogger):
    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)

    def get_sbom_path(self, repo_dir, repo, prep_step=None):
        self.logger.info(f"Ensuring SBOM exists for repo_id: {repo['repo_id']} (repo slug: {repo['repo_slug']}).")
        
        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        sbom_path = os.path.join(repo_dir, "sbom.json")
        lock_path = sbom_path + ".lock"

        # Fast path: if already exists, use immediately
        if os.path.exists(sbom_path):
            self.logger.debug(f"SBOM already exists at {sbom_path}")
            return sbom_path

        with FileLock(lock_path):
            # Inside lock, recheck
            if os.path.exists(sbom_path):
                self.logger.debug(f"SBOM already exists at {sbom_path} after lock acquisition")
                return sbom_path

            # Optional repo preparation (e.g., Maven effective-pom)
            if prep_step:
                self.logger.info(f"Running repo preparation step before SBOM generation for repo_id: {repo['repo_id']}.")
                prep_step(repo_dir)

            self.logger.info(f"Generating SBOM for repo_id: {repo['repo_id']}.")

            try:
                command = [
                    "syft",
                    repo_dir,
                    "--output", "json",
                    "--file", sbom_path
                ]
                self.logger.debug("Executing command: %s", " ".join(command))
                subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=Config.DEFAULT_PROCESS_TIMEOUT
                )
                self.logger.info(f"SBOM generated and saved at: {sbom_path}")
            except subprocess.TimeoutExpired as e:
                error_message = f"Syft command timed out for repo_id {repo['repo_id']} after {e.timeout} seconds."
                self.logger.error(error_message)
                raise RuntimeError(error_message)
            except subprocess.CalledProcessError as e:
                error_message = f"Syft command failed for repo_id {repo['repo_id']}: {e.stderr.strip()}"
                self.logger.error(error_message)
                raise RuntimeError(error_message)

        return sbom_path



