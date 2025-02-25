import subprocess
import os
import json
from sqlalchemy.dialects.postgresql import insert
from modular.shared.models import Session, GrypeResult
from modular.shared.execution_decorator import analyze_execution
from config.config import Config
from modular.shared.base_logger import BaseLogger
import logging

class GrypeAnalyzer(BaseLogger):
    def __init__(self, repo_id, repo_slug, logger=None):
        if logger is None:
            self.logger = self.get_logger("GrypeAnalyzer")
        else:
            self.logger = logger
        self.logger.setLevel(logging.DEBUG)
        self.repo_id = repo_id
        self.repo_slug = repo_slug

    @analyze_execution(session_factory=Session, stage="Grype Analysis")
    def run_analysis(self, repo_dir, repo, session, run_id=None):
        self.logger.info(f"Starting Grype analysis for repo_id: {self.repo_id} (repo slug: {repo.repo_slug}).")
        
        sbom_file_path = os.path.join(repo_dir, "sbom.json")
        grype_file_path = os.path.join(repo_dir, "grype-results.json")
        
        # Check if the SBOM file exists
        if not os.path.exists(sbom_file_path):
            error_message = f"SBOM file not found for repository {repo.repo_name} at path: {sbom_file_path}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)
        
        self.logger.info(f"Analyzing SBOM with Grype for repo_id: {self.repo_id} using SBOM at {sbom_file_path}.")

        try:
            env = os.environ.copy()
            env['GRYPE_DB_CACHE_DIR'] = Config.GRYPE_DB_CACHE_DIR
            self.logger.debug("Using GRYPE_DB_CACHE_DIR: %s", env['GRYPE_DB_CACHE_DIR'])
            command = [
                "grype",
                f"sbom:{sbom_file_path}",
                "--output", "json",
                "--file", grype_file_path
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
            self.logger.debug(f"Grype results written to: {grype_file_path}")
        except subprocess.TimeoutExpired as e:
            error_message = f"Grype command timed out for repo_id {self.repo_id} after {e.timeout} seconds."
            self.logger.error(error_message)
            raise RuntimeError(error_message)
        except subprocess.CalledProcessError as e:
            error_message = f"Grype command failed for repo_id {self.repo_id}: {e.stderr.strip()}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        if not os.path.exists(grype_file_path):
            error_message = f"Grype results file not found for repository {repo.repo_name}. Expected at: {grype_file_path}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        self.logger.info(f"Reading Grype results from disk for repo_id: {self.repo_id}.")
        try:
            grype_result = self.parse_and_save_grype_results(grype_file_path, self.repo_id, session)
        except Exception as e:
            error_message = f"Error while parsing or saving Grype results for repository {repo.repo_name}: {e}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        # If grype_result is a plain string (i.e. no vulnerabilities found), return it as is.
        if isinstance(grype_result, str):
            return grype_result
        else:
            return json.dumps(grype_result)

    def parse_and_save_grype_results(self, grype_file_path, repo_id, session):
        self.logger.info(f"Reading Grype results from: {grype_file_path}")
        try:
            with open(grype_file_path, "r") as file:
                grype_data = json.load(file)

            matches = grype_data.get("matches", [])
            if not matches:
                message = f"No vulnerabilities found for repo_id: {repo_id}"
                self.logger.info(message)
                return message

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
            return grype_data

        except Exception as e:
            self.logger.exception(f"Error while parsing or saving Grype results for repository ID {repo_id}: {e}")
            raise

if __name__ == "__main__":
    repo_id = "sonar-metrics"
    repo_slug = "sonar-metrics"
    repo_dir = "/tmp/sonar-metrics"  # Adjust this path as necessary

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug
            self.repo_name = repo_slug

    repo = MockRepo(repo_id, repo_slug)
    analyzer = GrypeAnalyzer(repo_id, repo_slug)
    session = Session()

    try:
        analyzer.logger.info(f"Starting standalone Grype analysis for repo_id: {repo.repo_id}.")
        result = analyzer.run_analysis(repo_dir, repo=repo, session=session, run_id="STANDALONE_RUN_001")
        analyzer.logger.info(f"Standalone Grype analysis result:\n{result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone Grype analysis: {e}")
    finally:
        session.close()
        analyzer.logger.info(f"Database session closed for repo_id: {repo.repo_id}.")