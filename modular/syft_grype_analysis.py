import subprocess
import csv
import os
import json
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import insert
from modular.models import Session, GrypeResult
from modular.execution_decorator import analyze_execution
from modular.config import Config
from modular.base_logger import BaseLogger  # Assuming BaseLogger is correctly implemented and available
import logging

class SyftAndGrypeAnalyzer(BaseLogger):

    def __init__(self):
        self.logger = self.get_logger("SyftAndGrypeAnalyzer")
        self.logger.setLevel(logging.WARN)  # Default logging level

    @analyze_execution(session_factory=Session, stage="Syft and Grype Analysis")
    def run_analysis(self, repo_dir, repo, session, run_id=None):
        self.logger.info(f"Starting Syft and Grype analysis for repo_id: {repo.repo_id} (repo_slug: {repo.repo_slug}).")

        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        sbom_file_path = os.path.join(repo_dir, "sbom.json")
        self.logger.info(f"Generating SBOM for repo_id: {repo.repo_id} using Syft.")
        try:
            subprocess.run(
                ["syft", repo_dir, "--output", "json", "--file", sbom_file_path],
                capture_output=True,
                text=True,
                check=True,
            )
            self.logger.debug(f"SBOM successfully generated at: {sbom_file_path}")
        except subprocess.CalledProcessError as e:
            error_message = f"Syft command failed for repo_id {repo.repo_id}: {e.stderr.strip()}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        grype_file_path = os.path.join(repo_dir, "grype-results.json")
        self.logger.info(f"Analyzing SBOM with Grype for repo_id: {repo.repo_id}.")
        try:
            subprocess.run(
                ["grype", f"sbom:{sbom_file_path}", "--output", "json", "--file", grype_file_path],
                capture_output=True,
                text=True,
                check=True,
            )
            self.logger.debug(f"Grype results written to: {grype_file_path}")
        except subprocess.CalledProcessError as e:
            error_message = f"Grype command failed for repo_id {repo.repo_id}: {e.stderr.strip()}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        if not os.path.exists(grype_file_path):
            error_message = f"Grype results file not found for repository {repo.repo_name}. Expected at: {grype_file_path}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        self.logger.info(f"Reading Grype results from disk for repo_id: {repo.repo_id}.")
        try:
            processed_vulnerabilities = self.parse_and_save_grype_results(grype_file_path, repo.repo_id, session)
        except Exception as e:
            error_message = f"Error while parsing or saving Grype results for repository {repo.repo_name}: {e}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        return f"{processed_vulnerabilities} vulnerabilities processed"

    def parse_and_save_grype_results(self, grype_file_path, repo_id, session):
        self.logger.info(f"Reading Grype results from: {grype_file_path}")
        try:
            with open(grype_file_path, "r") as file:
                grype_data = json.load(file)

            matches = grype_data.get("matches", [])
            if not matches:
                self.logger.info(f"No vulnerabilities found for repo_id: {repo_id}")
                return 0

            self.logger.debug(f"Found {len(matches)} vulnerabilities for repo_id: {repo_id}.")
            processed_vulnerabilities = 0

            for match in matches:
                vulnerability = match.get("vulnerability", {})
                artifact = match.get("artifact", {})
                locations = artifact.get("locations", [{}])

                cve = vulnerability.get("id", "No CVE")
                description = vulnerability.get("description", "No description provided")
                severity = vulnerability.get("severity", "UNKNOWN")
                package = artifact.get("name", "Unknown")
                version = artifact.get("version", "Unknown")
                file_path = locations[0].get("path", "N/A") if locations else "N/A"
                language = artifact.get("language", "Unknown")

                # Extract fix metadata
                fix_data = vulnerability.get("fix", {})
                fix_versions_list = fix_data.get("versions", [])
                fix_versions = ", ".join(fix_versions_list)
                fix_state = fix_data.get("state", "not fixed")

                self.logger.debug(f"Extracted fix_versions for CVE {cve}: {fix_versions}")

                session.execute(
                    insert(GrypeResult).values(
                        repo_id=repo_id,
                        cve=cve,
                        description=description,
                        severity=severity,
                        package=package,
                        version=version,
                        file_path=file_path,
                        language=language,
                        fix_versions=fix_versions,
                        fix_state=fix_state,
                    ).on_conflict_do_update(
                        index_elements=["repo_id", "cve", "package", "version"],
                        set_={
                            "description": description,
                            "severity": severity,
                            "file_path": file_path,
                            "language": language,
                            "fix_versions": fix_versions,
                            "fix_state": fix_state,
                        },
                    )
                )
                processed_vulnerabilities += 1

            session.commit()
            self.logger.debug(f"Grype results successfully committed for repo_id: {repo_id}.")
            return processed_vulnerabilities

        except Exception as e:
            self.logger.exception(f"Error while parsing or saving Grype results for repository ID {repo_id}: {e}")
            raise


if __name__ == "__main__":
    repo_slug = "WebGoat"
    repo_id = "WebGoat"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug
            self.repo_name = repo_slug

    analyzer = SyftAndGrypeAnalyzer()
    repo = MockRepo(repo_id, repo_slug)
    repo_dir = f"/tmp/{repo.repo_slug}"
    session = Session()

    try:
        analyzer.logger.info(f"Starting standalone Syft and Grype analysis for repo_id: {repo.repo_id}.")
        result = analyzer.run_analysis(repo_dir, repo=repo, session=session, run_id="STANDALONE_RUN_001")
        analyzer.logger.info(f"Standalone Syft and Grype analysis result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone Syft and Grype analysis: {e}")
    finally:
        session.close()
        analyzer.logger.info(f"Database session closed for repo_id: {repo.repo_id}.")
