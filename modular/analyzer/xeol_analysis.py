import subprocess
import os
import json
from sqlalchemy.dialects.postgresql import insert
from modular.shared.models import Session, XeolResult
from modular.shared.execution_decorator import analyze_execution
from config.config import Config
from modular.shared.base_logger import BaseLogger
import logging

class XeolAnalyzer(BaseLogger):

    def __init__(self, logger=None):
        if logger is None:
            self.logger = self.get_logger("SyftAndXeolAnalyzer")
        else:
            self.logger = logger
        self.logger.setLevel(logging.DEBUG)

    @analyze_execution(session_factory=Session, stage="Syft and Xeol Analysis")
    def run_analysis(self, repo_dir, repo, session, run_id=None):

        self.logger.info(f"Repo slug: {repo.repo_slug}.")
        self.logger.info(f"Starting Syft and Xeol analysis for repo_id: {repo.repo_id}.")

        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        # Generate SBOM using Syft
        sbom_file_path = os.path.join(repo_dir, "sbom.json")
        self.logger.info(f"Generating SBOM for repo_id: {repo.repo_id} using Syft.")

        try:
            command = [
                "syft",
                repo_dir,
                "--output", "json",
                "--file",
                sbom_file_path
            ]
            self.logger.debug("Executing command: %s", " ".join(command))
            subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                timeout=Config.DEFAULT_PROCESS_TIMEOUT
            )
            self.logger.debug(f"SBOM successfully generated at: {sbom_file_path}")
        except subprocess.TimeoutExpired as e:
            error_message = f"Syft command timed out for repo_id {repo.repo_id} after {e.timeout} seconds."
            self.logger.error(error_message)
            raise RuntimeError(error_message)
        except subprocess.CalledProcessError as e:
            error_message = f"Syft command failed for repo_id {repo.repo_id}: {e.stderr.strip()}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        # Run Xeol on the generated SBOM
        xeol_file_path = os.path.join(repo_dir, "xeol-results.json")
        self.logger.info(f"Analyzing SBOM with Xeol for repo_id: {repo.repo_id}.")

        try:
            env = os.environ.copy()
            env['XEOL_DB_CACHE_DIR'] = Config.XEOL_DB_CACHE_DIR
            self.logger.debug("Using XEOL_DB_CACHE_DIR: %s", env['XEOL_DB_CACHE_DIR'])
            command = [
                "xeol",
                f"sbom:{sbom_file_path}",
                "--output", "json",
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
            error_message = f"Xeol command failed for repo_id {repo.repo_id}: {e.stderr.strip()}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)
        except subprocess.TimeoutExpired as e:
            error_message = f"Xeol command timed out for repo_id {repo.repo_id} after {e.timeout} seconds."
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        if not os.path.exists(xeol_file_path):
            error_message = f"Xeol results file not found for repository {repo.repo_name}. Expected at: {xeol_file_path}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        self.logger.info(f"Reading Xeol results from disk for repo_id: {repo.repo_id}.")
        try:
            xeol_data = self.parse_and_save_xeol_results(xeol_file_path, repo.repo_id, session)
        except Exception as e:
            error_message = f"Error while parsing or saving Xeol results for repository {repo.repo_name}: {e}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        return json.dumps(xeol_data)

    def parse_and_save_xeol_results(self, xeol_file_path, repo_id, session):
        self.logger.info(f"Parsing Xeol results from: {xeol_file_path}")
        try:
            with open(xeol_file_path, "r") as file:
                xeol_data = json.load(file)

            matches = xeol_data.get("matches", [])
            if not matches:
                self.logger.info(f"No matches found in Xeol results for repo_id: {repo_id}")
                return xeol_data

            self.logger.debug(f"Found {len(matches)} matches in Xeol results for repo_id: {repo_id}.")
            for match in matches:
                # Extract lifecycle info from "Cycle"
                cycle = match.get("Cycle", {})
                product_name = cycle.get("ProductName", "Unknown")
                product_permalink = cycle.get("ProductPermalink", "Unknown")
                release_cycle = cycle.get("ReleaseCycle", "Unknown")
                eol_date = cycle.get("Eol", "Unknown")
                latest_release = cycle.get("LatestRelease", "Unknown")
                latest_release_date = cycle.get("LatestReleaseDate", "Unknown")
                release_date = cycle.get("ReleaseDate", "Unknown")

                # Extract artifact details
                artifact = match.get("artifact", {})
                artifact_name = artifact.get("name", "Unknown")
                artifact_version = artifact.get("version", "Unknown")
                artifact_type = artifact.get("type", "Unknown")
                locations = artifact.get("locations", [])
                file_path = locations[0].get("path", "N/A") if locations else "N/A"
                language = artifact.get("language", "Unknown")

                self.logger.debug(f"Inserting Xeol result for artifact {artifact_name} version {artifact_version}.")

                session.execute(
                    insert(XeolResult).values(
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
                    ).on_conflict_do_update(
                        index_elements=["repo_id", "artifact_name", "artifact_version"],
                        set_={
                            "product_name": product_name,
                            "product_permalink": product_permalink,
                            "release_cycle": release_cycle,
                            "eol_date": eol_date,
                            "latest_release": latest_release,
                            "latest_release_date": latest_release_date,
                            "release_date": release_date,
                            "artifact_type": artifact_type,
                            "file_path": file_path,
                            "language": language,
                        },
                    )
                )
            session.commit()
            self.logger.debug(f"Xeol results successfully committed for repo_id: {repo_id}.")
            return xeol_data

        except Exception as e:
            self.logger.exception(f"Error while parsing or saving Xeol results for repository ID {repo_id}: {e}")
            raise


if __name__ == "__main__":
    repo_slug = "sonar-metrics"
    repo_id = "sonar-metrics"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug
            self.repo_name = repo_slug

    analyzer = SyftAndXeolAnalyzer()
    repo = MockRepo(repo_id, repo_slug)
    repo_dir = f"/tmp/{repo.repo_slug}"
    session = Session()

    try:
        analyzer.logger.info(f"Starting standalone Syft and Xeol analysis for repo_id: {repo.repo_id}.")
        result = analyzer.run_analysis(repo_dir, repo=repo, session=session, run_id="STANDALONE_RUN_001")
        analyzer.logger.info(f"Standalone Syft and Xeol analysis result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone Syft and Xeol analysis: {e}")
    finally:
        session.close()
        analyzer.logger.info(f"Database session closed for repo_id: {repo.repo_id}.")
