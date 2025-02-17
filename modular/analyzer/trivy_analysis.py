import os
import json
import logging
import subprocess
import shutil
from sqlalchemy.dialects.postgresql import insert
from modular.shared.execution_decorator import analyze_execution
from modular.shared.models import Session, TrivyVulnerability
from config.config import Config
from modular.shared.base_logger import BaseLogger  # Import the BaseLogger

class TrivyAnalyzer(BaseLogger):

    def __init__(self, logger=None):
        if logger is None:
            self.logger = self.get_logger("TrivyAnalyzer")
        else:
            self.logger = logger
        self.logger.setLevel(logging.INFO)

    @analyze_execution(session_factory=Session, stage="Trivy Analysis")
    def run_analysis(self, repo_dir, repo, session, run_id=None):
        self.logger.info(f"Starting Trivy analysis for repo_id: {repo.repo_id} (repo_slug: {repo.repo_slug}).")

        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        self.logger.info(f"Executing Trivy command in directory: {repo_dir}")
        try:

            env = os.environ.copy()
            env['TRIVY_CACHE_DIR'] = Config.TRIVY_CACHE_DIR

            result = subprocess.run(
                [
                    "trivy",
                    "repo",
                    "--skip-db-update",
                    "--skip-java-db-update",
                    "--offline-scan",
                    "--format", "json",
                    repo_dir
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=300
            )

            if result.returncode != 0:
                error_message = (f"Trivy command failed for repo_id {repo.repo_id}. "
                                 f"Return code: {result.returncode}. Error: {result.stderr.strip()}")
                self.logger.error(error_message)
                raise RuntimeError(error_message)

            self.logger.debug(f"Trivy command completed successfully for repo_id: {repo.repo_id}")

        except subprocess.TimeoutExpired as e:
            error_message = f"Trivy command timed out for repo_id {repo.repo_id} after {e.timeout} seconds."
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        stdout_str = result.stdout.strip()
        if not stdout_str:
            error_message = f"No output from Trivy command for repo_id: {repo.repo_id}"
            self.logger.error(error_message)
            raise ValueError(error_message)

        self.logger.info(f"Parsing Trivy output for repo_id: {repo.repo_id}")
        try:
            trivy_data = json.loads(stdout_str)
        except json.JSONDecodeError as e:
            error_message = f"Error decoding Trivy JSON output: {str(e)}"
            self.logger.error(error_message)
            raise ValueError(error_message)

        self.logger.info(f"Saving Trivy vulnerabilities to the database for repo_id: {repo.repo_id}")
        try:
            total_vulnerabilities = self.save_trivy_results(session, repo.repo_id, trivy_data)
        except Exception as e:
            error_message = f"Error saving Trivy vulnerabilities: {str(e)}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        return json.dumps(trivy_data)


    def prepare_trivyignore(self, repo_dir):

        trivyignore_path = os.path.join(repo_dir, ".trivyignore")

        if os.path.exists(trivyignore_path):
            self.logger.info(f".trivyignore already exists in {repo_dir}")
            return
        try:
            shutil.copy(Config.TRIVYIGNORE_TEMPLATE, trivyignore_path)
            self.logger.info(f"Copied .trivyignore to {repo_dir}")
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")

    def save_trivy_results(self, session, repo_id, results):
        self.logger.debug(f"Processing Trivy vulnerabilities for repo_id: {repo_id}")
        try:
            total_vulnerabilities = 0
            for item in results.get("Results", []):
                target = item.get("Target")
                vulnerabilities = item.get("Vulnerabilities", [])
                resource_class = item.get("Class", None)
                resource_type = item.get("Type", None)

                for vuln in vulnerabilities:
                    total_vulnerabilities += 1
                    session.execute(
                        insert(TrivyVulnerability).values(
                            repo_id=repo_id,
                            target=target,
                            resource_class=resource_class,
                            resource_type=resource_type,
                            vulnerability_id=vuln.get("VulnerabilityID"),
                            pkg_name=vuln.get("PkgName"),
                            installed_version=vuln.get("InstalledVersion"),
                            fixed_version=vuln.get("FixedVersion"),
                            severity=vuln.get("Severity"),
                            primary_url=vuln.get("PrimaryURL"),
                            description=vuln.get("Description"),
                        ).on_conflict_do_update(
                            index_elements=["repo_id", "vulnerability_id", "pkg_name"],
                            set_={
                                "resource_class": resource_class,
                                "resource_type": resource_type,
                                "installed_version": vuln.get("InstalledVersion"),
                                "fixed_version": vuln.get("FixedVersion"),
                                "severity": vuln.get("Severity"),
                                "primary_url": vuln.get("PrimaryURL"),
                                "description": vuln.get("Description"),
                            }
                        )
                    )

            session.commit()
            self.logger.debug(f"Trivy vulnerabilities committed to the database for repo_id: {repo_id}")
            return total_vulnerabilities

        except Exception as e:
            self.logger.exception(f"Error saving Trivy vulnerabilities for repo_id {repo_id}: {e}")
            error_message = f"Error saving Trivy vulnerabilities for repo_id {repo_id}: {e}"
            raise RuntimeError(error_message)


if __name__ == "__main__":
    repo_slug = "WebGoat"
    repo_id = "WebGoat"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug
            self.repo_name = repo_slug

    analyzer = TrivyAnalyzer()
    repo = MockRepo(repo_id, repo_slug)
    repo_dir = f"/tmp/{repo.repo_slug}"
    session = Session()

    try:
        analyzer.logger.info(f"Starting standalone Trivy analysis for repo_id: {repo.repo_id}")
        result = analyzer.run_analysis(repo_dir, repo=repo, session=session, run_id="STANDALONE_RUN_001")
        analyzer.logger.info(f"Standalone Trivy analysis result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone Trivy analysis: {e}")
    finally:
        session.close()
        analyzer.logger.info(f"Database session closed for repo_id: {repo.repo_id}")
