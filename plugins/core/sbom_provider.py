import os
from filelock import FileLock
from pathlib import Path

from plugins.core.sbom.sbom_utils import is_gradle_project, has_gradle_lockfile, is_maven_project
from plugins.core.sbom.gradle_sbom_generator import GradleSbomGenerator
from plugins.core.sbom.maven_helper import prepare_maven_project
from plugins.core.sbom.syft_helper import run_syft
from shared.base_logger import BaseLogger

class SBOMProvider(BaseLogger):
    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)

    def ensure_sbom(self, repo_dir: str, repo: dict) -> str:
        """
        Ensures that an SBOM exists for the given repository.
        Will generate it if missing, using the appropriate strategy.
        """
        with self._get_file_lock(repo_dir):
            sbom_path = os.path.join(repo_dir, "sbom.json")

            if os.path.exists(sbom_path):
                self.logger.info(f"SBOM already exists for repo_id: {repo['repo_id']}. Skipping generation.")
                return sbom_path

            self.logger.info(f"Preparing SBOM for repo_id: {repo['repo_id']} (repo slug: {repo['repo_slug']}).")

            if is_gradle_project(repo_dir):
                if has_gradle_lockfile(repo_dir):
                    self.logger.info(f"Gradle project with lockfile detected for {repo['repo_id']}. Running Syft.")
                    run_syft(repo_dir)
                else:
                    self.logger.info(f"Gradle project without lockfile detected for {repo['repo_id']}. Generating manual SBOM.")
                    GradleSbomGenerator(logger=self.logger, run_id=self.run_id).run_analysis(repo_dir, repo)

            elif is_maven_project(repo_dir):
                self.logger.info(f"Maven project detected for {repo['repo_id']}. Preparing effective-pom and running Syft.")
                prepare_maven_project(repo_dir)
                run_syft(repo_dir)

            else:
                self.logger.info(f"Unknown or other project type detected for {repo['repo_id']}. Running Syft.")
                run_syft(repo_dir)

            if not os.path.exists(sbom_path):
                raise FileNotFoundError(f"SBOM generation failed for repo_id {repo['repo_id']}.")

            self.logger.info(f"SBOM prepared at {sbom_path} for repo_id {repo['repo_id']}.")
            return sbom_path

    def _get_file_lock(self, repo_dir: str):
        """
        Returns a file lock object to prevent concurrent SBOM generation.
        """
        lock_file_path = os.path.join(repo_dir, "sbom.lock")
        lock = FileLock(lock_file_path)
        return lock
        
        
if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python sbom_provider.py /path/to/repo_dir")
        sys.exit(1)

    repo_dir = sys.argv[1]
    repo_name = os.path.basename(os.path.normpath(repo_dir))
    repo_slug = repo_name
    repo_id = f"standalone_test/{repo_slug}"

    repo = {
        "repo_id": repo_id,
        "repo_slug": repo_slug,
        "repo_name": repo_name
    }

    sbom_provider = SBOMProvider(run_id="STANDALONE_RUN_ID_001")

    try:
        print(f"Starting standalone SBOM preparation for repo_id: {repo['repo_id']}")
        sbom_path = sbom_provider.ensure_sbom(repo_dir, repo)
        print(f"Standalone SBOM prepared successfully at: {sbom_path}")
    except Exception as e:
        print(f"Error during standalone SBOM preparation: {e}")