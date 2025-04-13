import os
from filelock import FileLock
from pathlib import Path
from plugins.core.sbom.sbom_utils import is_gradle_project, has_gradle_lockfile, is_maven_project
from plugins.core.sbom.gradle_sbom_generator import GradleSbomGenerator
from plugins.core.sbom.maven_helper import prepare_maven_project
from plugins.core.sbom.syft_helper import run_syft
from shared.base_logger import BaseLogger
import logging
import sys

class SBOMProvider(BaseLogger):
    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)

    def ensure_sbom(self, repo_dir: str, repo: dict) -> str:

        self.logger.info(f"Starting ensure_sbom for {repo['repo_id']}")

        sbom_path = os.path.join(repo_dir, "sbom.json")
        lock_path = sbom_path + ".lock"

        if os.path.exists(sbom_path):
            self.logger.debug(f"SBOM exists at {sbom_path} (size: {os.path.getsize(sbom_path)} bytes, modified: {os.path.getmtime(sbom_path)})")
            self.logger.info(f"Using existing SBOM for {repo['repo_id']}")
            return sbom_path

        self.logger.debug(f"Acquiring file lock: {lock_path}")
        with FileLock(lock_path, timeout=60):
            self.logger.debug(f"Lock acquired for {repo['repo_id']}")

            if os.path.exists(sbom_path):
                self.logger.warning(f"SBOM created by parallel process for {repo['repo_id']}")
                return sbom_path

            self.logger.info(f"Starting SBOM generation for {repo['repo_id']}")

            try:
                if is_gradle_project(repo_dir):
                    self._handle_gradle_project(repo_dir, repo)
                elif is_maven_project(repo_dir):
                    self._handle_maven_project(repo_dir)
                else:
                    self.logger.warning(f"Unknown project type for {repo['repo_id']}")
                    run_syft(repo_dir)

                if not os.path.exists(sbom_path):
                    raise FileNotFoundError(f"SBOM file not created at {sbom_path}")

                self.logger.debug(f"SBOM generation completed ({os.path.getsize(sbom_path)} bytes)")
                return sbom_path

            except Exception as e:
                self.logger.error(f"SBOM generation failed for {repo['repo_id']}: {str(e)}", exc_info=True)
                raise

    def _handle_gradle_project(self, repo_dir: str, repo: dict):
        if has_gradle_lockfile(repo_dir):
            self.logger.debug(f"Found Gradle lockfile in {repo_dir}")
            self.logger.info(f"Running Syft on Gradle project {repo['repo_id']}")
            run_syft(repo_dir)
        else:
            self.logger.warning(f"No Gradle lockfile found in {repo_dir}")
            self.logger.info(f"Starting manual Gradle SBOM generation for {repo['repo_id']}")
            GradleSbomGenerator(logger=self.logger, run_id=self.run_id).run_analysis(repo_dir, repo)

    def _handle_maven_project(self, repo_dir: str):
        self.logger.debug("Preparing Maven effective POM")
        self.logger.info(f"Processing Maven project in {repo_dir}")
        prepare_maven_project(repo_dir)
        self.logger.debug("Running Syft on Maven project")
        run_syft(repo_dir)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python sbom_provider.py /path/to/repo_dir")
        sys.exit(1)

    repo_dir = sys.argv[1]
    repo_name = os.path.basename(os.path.normpath(repo_dir))
    
    repo = {
        "repo_id": f"standalone_test/{repo_name}",
        "repo_slug": repo_name,
        "repo_name": repo_name
    }

    sbom_provider = SBOMProvider(run_id="STANDALONE_RUN_ID_001")
    sbom_provider.logger.addHandler(logging.StreamHandler())
    
    try:
        sbom_provider.logger.debug(f"Starting SBOM process with args: {sys.argv}")
        sbom_provider.logger.info(f"SBOM generation initiated for {repo_dir}")
        sbom_path = sbom_provider.ensure_sbom(repo_dir, repo)
        sbom_provider.logger.info(f"SBOM generation successful: {sbom_path}")
        print(f"SBOM created at {sbom_path}")
    except Exception as e:
        sbom_provider.logger.critical(f"SBOM process failed: {str(e)}", exc_info=True)
        sys.exit(1)
