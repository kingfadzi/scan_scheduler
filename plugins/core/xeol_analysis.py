import subprocess
import json

from shared.models import Session, XeolResult
from shared.execution_decorator import analyze_execution
from config.config import Config
from shared.base_logger import BaseLogger
import logging
from plugins.core.sbom.sbom_provider import SBOMProvider


class XeolAnalyzer(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)
        self.sbom_provider = SBOMProvider(logger=self.logger, run_id=self.run_id) 

    @analyze_execution(session_factory=Session, stage="Xeol Analysis")
    def run_analysis(self, repo_dir, repo, run_id=None):

        self.logger.info(f"Repo slug: {repo['repo_slug']}.")
        self.logger.info(f"Starting Xeol analysis for repo_id: {repo['repo_id']}.")

        sbom_file_path = self.sbom_provider.ensure_sbom(repo_dir, repo)

        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)
      
        if not os.path.exists(sbom_file_path):
            error_message = f"SBOM file does not exist: {sbom_file_path}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)
        self.logger.info(f"SBOM file found at {sbom_file_path} for repo_id: {repo['repo_id']}.")

        xeol_file_path = os.path.join(repo_dir, "xeol-results.json")
        self.logger.info(f"Analyzing SBOM with Xeol for repo_id: {repo['repo_id']}.")

        try:
            env = os.environ.copy()
            env['XEOL_DB_CACHE_DIR'] = Config.XEOL_DB_CACHE_DIR
            self.logger.debug("Using XEOL_DB_CACHE_DIR: %s", env['XEOL_DB_CACHE_DIR'])
            command = [
                "xeol",
                f"sbom:{sbom_file_path}",
                "--output", "json",
                "-vv",
                "--file", xeol_file_path
            ]
            self.logger.debug("Executing command: %s", " ".join(command))
            subprocess.run(
                command,
                env=env,
                capture_output=True,
                text=True,
                check=True,
                timeout=300
            )
            self.logger.debug(f"Xeol results written to: {xeol_file_path}")
        except subprocess.CalledProcessError as e:
            error_message = f"Xeol command failed for repo_id {repo['repo_id']}: {e.stderr.strip()}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)
        except subprocess.TimeoutExpired as e:
            error_message = f"Xeol command timed out for repo_id {repo['repo_id']} after {e.timeout} seconds."
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        if not os.path.exists(xeol_file_path):
            error_message = f"Xeol results file not found for repository {repo['repo_name']}. Expected at: {xeol_file_path}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        self.logger.info(f"Reading Xeol results from disk for repo_id: {repo['repo_id']}.")
        try:
            xeol_data = self.parse_and_save_xeol_results(xeol_file_path, repo['repo_id'])
        except Exception as e:
            error_message = f"Error while parsing or saving Xeol results for repository {repo['repo_name']}: {e}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        return json.dumps(xeol_data)

    def parse_and_save_xeol_results(self, xeol_file_path, repo_id):
        session = None
        try:
            with open(xeol_file_path, "r") as file:
                xeol_data = json.load(file)

            matches = xeol_data.get("matches", [])
            eol_count = len(matches)
            message = f"Found {eol_count} EOL dependencies for repo_id: {repo_id}"

            if not matches:
                self.logger.info(f"No matches found in EOL results for repo_id: {repo_id}")
                return message

            session = Session()
            session.query(XeolResult).filter(
                XeolResult.repo_id == repo_id
            ).delete()

            for match in matches:
                cycle = match.get("Cycle", {})
                product_name = cycle.get("ProductName", "Unknown")
                product_permalink = cycle.get("ProductPermalink", "Unknown")
                release_cycle = cycle.get("ReleaseCycle", "Unknown")
                eol_date = cycle.get("Eol", "Unknown")
                latest_release = cycle.get("LatestRelease", "Unknown")
                latest_release_date = cycle.get("LatestReleaseDate", "Unknown")
                release_date = cycle.get("ReleaseDate", "Unknown")

                artifact = match.get("artifact", {})
                artifact_name = artifact.get("name", "Unknown")
                artifact_version = artifact.get("version", "Unknown")
                artifact_type = artifact.get("type", "Unknown")
                locations = artifact.get("locations", [])
                file_path = locations[0].get("path", "N/A") if locations else "N/A"
                language = artifact.get("language", "Unknown")

                xeol_result = XeolResult(
                    repo_id=repo_id,
                    product_name=product_name,
                    product_permalink=product_permalink,
                    release_cycle=release_cycle,
                    eol_date=eol_date,
                    latest_release=latest_release,
                    latest_release_date=latest_release_date,
                    release_date=release_date,
                    artifact_name=artifact_name,
                    artifact_version=artifact_version,
                    artifact_type=artifact_type,
                    file_path=file_path,
                    language=language,
                )
                session.add(xeol_result)

            session.commit()
            self.logger.debug(f"EOL results successfully committed for repo_id: {repo_id}.")
            return message

        except Exception as e:
            if session:
                session.rollback()
            self.logger.exception(f"Error while parsing or saving EOL results for repository ID {repo_id}: {e}")
            raise
        finally:
            if session:
                session.close()

import sys
import os

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py /path/to/repo_dir")
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

    session = Session()
    analyzer = XeolAnalyzer(run_id="STANDALONE_RUN_001")

    try:
        analyzer.logger.info(f"Starting standalone Xeol analysis for repo_dir: {repo_dir}, repo_id: {repo['repo_id']}.")
        result = analyzer.run_analysis(repo_dir, repo=repo)
        analyzer.logger.info(f"Standalone Xeol analysis result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone Xeol analysis: {e}")
    finally:
        session.close()
        analyzer.logger.info(f"Database session closed for repo_id: {repo['repo_id']}.")

