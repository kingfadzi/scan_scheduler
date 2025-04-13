import os
import json
import subprocess
from pathlib import Path

from filelock import FileLock

from plugins.core.sbom.gradle_sbom_generator import GradleSbomGenerator
from plugins.core.sbom.sbom_utils import has_gradle_lockfile, is_gradle_project
from plugins.core.sbom.maven_helper import prepare_maven_project
from plugins.core.sbom.syft_runner import run_syft
from shared.base_logger import BaseLogger

class SBOMProvider(BaseLogger):
    """
    Provides SBOM generation and merging for mixed-technology repositories.
    Handles Gradle (manual), Maven (effective-pom), and others via Syft.
    """

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(os.getenv('LOGLEVEL', 'DEBUG'))

    def ensure_sbom(self, repo_dir: str, repo: dict) -> str:
        """
        Ensures a unified SBOM exists for the given repository.
        If missing, generates it by handling Gradle, Maven, and other tech stacks appropriately.
        """
        sbom_path = os.path.join(repo_dir, "sbom.json")
        lock_path = os.path.join(repo_dir, "sbom.lock")

        with FileLock(lock_path):
            if os.path.exists(sbom_path):
                self.logger.info(f"SBOM already exists for repo_id: {repo['repo_id']}. Skipping generation.")
                return sbom_path

            self.logger.info(f"Preparing unified SBOM for repo_id: {repo['repo_id']} (repo slug: {repo['repo_slug']}).")

            gradle_sbom_paths = []

            # Step 1: Handle Gradle modules manually if needed
            for gradle_dir in self._find_gradle_modules(repo_dir):
                if not has_gradle_lockfile(gradle_dir):
                    self.logger.info(f"Gradle project without lockfile detected at {gradle_dir}. Generating manual SBOM.")
                    gradle_generator = GradleSbomGenerator(logger=self.logger, run_id=self.run_id)
                    gradle_generator.run_analysis(gradle_dir, repo)

                    gradle_sbom = os.path.join(gradle_dir, "sbom.json")
                    if os.path.exists(gradle_sbom):
                        gradle_sbom_paths.append(gradle_sbom)

            # Step 2: Handle Maven (only root-level pom.xml)
            root_pom = os.path.join(repo_dir, "pom.xml")
            if os.path.exists(root_pom):
                self.logger.info(f"Root-level Maven pom.xml detected at {repo_dir}. Running effective-pom preparation.")
                prepare_maven_project(repo_dir, logger=self.logger)

            # Step 3: Full repo Syft scan
            syft_sbom_path = os.path.join(repo_dir, "sbom-syft.json")
            self.logger.info(f"Running Syft full repo scan to capture all ecosystems.")
            run_syft(repo_dir, output_path=syft_sbom_path, logger=self.logger)

            if not os.path.exists(syft_sbom_path):
                raise FileNotFoundError(f"Syft SBOM generation failed for repo_id {repo['repo_id']}.")

            # Step 4: Merge all SBOMs (Gradle + Syft) into final sbom.json
            self._merge_sboms([syft_sbom_path] + gradle_sbom_paths, sbom_path)

            self.logger.info(f"Unified SBOM ready at {sbom_path} for repo_id: {repo['repo_id']}.")

            return sbom_path

    def _find_gradle_modules(self, root_dir: str) -> list:
        gradle_dirs = []
        for path in Path(root_dir).rglob("build.gradle*"):
            if path.is_file():
                gradle_dirs.append(str(path.parent))
        return gradle_dirs

    def _merge_sboms(self, sbom_paths: list, output_path: str):
        merged_sbom = {
            "artifacts": [],
            "source": {
                "type": "multi-repo",
                "description": "Merged SBOM from multiple projects"
            },
            "descriptor": {
                "name": "merged-sbom",
                "version": "1.0.0",
                "configuration": {}
            },
            "schema": {
                "version": "16.0.24",
                "url": "https://raw.githubusercontent.com/anchore/syft/main/schema/json/schema-16.0.24.json"
            }
        }

        seen = set()

        for sbom_path in sbom_paths:
            with open(sbom_path, "r") as f:
                sbom_data = json.load(f)
                artifacts = sbom_data.get("artifacts", [])
                for artifact in artifacts:
                    # Optional deduplication based on purl or name+version
                    purl = artifact.get("purl") or f"{artifact.get('name')}@{artifact.get('version')}"
                    if purl not in seen:
                        merged_sbom["artifacts"].append(artifact)
                        seen.add(purl)

        with open(output_path, "w") as f:
            json.dump(merged_sbom, f, indent=2)

        self.logger.info(f"Merged {len(sbom_paths)} SBOMs into final {output_path} ({len(merged_sbom['artifacts'])} unique artifacts).")
        
import sys

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python sbom_provider.py /path/to/repo_dir")
        sys.exit(1)

    repo_dir = sys.argv[1]
    if not os.path.exists(repo_dir):
        print(f"Provided repo_dir does not exist: {repo_dir}")
        sys.exit(1)

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
        sbom_provider.logger.info(f"Starting standalone SBOM preparation for repo_id: {repo['repo_id']}")
        sbom_path = sbom_provider.ensure_sbom(repo_dir, repo)
        sbom_provider.logger.info(f"Standalone SBOM prepared successfully at: {sbom_path}")
    except Exception as e:
        sbom_provider.logger.error(f"Error during standalone SBOM preparation: {str(e)}", exc_info=True)
        sys.exit(1)