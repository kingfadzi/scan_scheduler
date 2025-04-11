import os
import json
import logging
import subprocess
import shutil

from sqlalchemy.dialects.postgresql import insert
from plugins.core.syft_analysis import SyftAnalyzer
from shared.execution_decorator import analyze_execution
from shared.models import Session, TrivyVulnerability
from config.config import Config
from shared.base_logger import BaseLogger


class TrivyAnalyzer(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)

    @analyze_execution(session_factory=Session, stage="Trivy Analysis")
    def run_analysis(self, repo_dir, repo):
        self.logger.info(f"Starting Trivy analysis for repo_id: {repo['repo_id']}")

        self.prepare_trivyignore(repo_dir)
        self.generate_sbom(repo_dir, repo)
        self.run_trivy_scan(repo_dir, repo)
        trivy_data = self.parse_trivy_output(repo_dir, repo)
        total_vulnerabilities = self.save_trivy_results(repo['repo_id'], trivy_data)

        self.logger.info(f"Found {total_vulnerabilities} vulnerabilities for repo_id: {repo['repo_id']}")
        return f"Found {total_vulnerabilities} vulnerabilities."

    def prepare_trivyignore(self, repo_dir):

        trivyignore_path = os.path.join(repo_dir, ".trivyignore")
        if not os.path.exists(trivyignore_path):
            try:
                shutil.copy(Config.TRIVYIGNORE_TEMPLATE, trivyignore_path)
                self.logger.info(f"Copied .trivyignore to {repo_dir}")
            except Exception as e:
                self.logger.error(f"Failed to copy .trivyignore: {e}")

    def generate_sbom(self, repo_dir, repo):

        syft_analyzer = SyftAnalyzer(logger=self.logger, run_id=self.run_id)
        syft_analyzer.generate_sbom(repo_dir=repo_dir, repo=repo)

    def run_trivy_scan(self, repo_dir, repo):

        if not os.path.exists(repo_dir):
            raise FileNotFoundError(f"Repository directory does not exist: {repo_dir}")

        output_file = os.path.join(repo_dir, "trivy_report.json")
        env = os.environ.copy()
        env['TRIVY_CACHE_DIR'] = Config.TRIVY_CACHE_DIR

        command = [
            "trivy",
            "repo",
            "--skip-db-update",
            "--skip-java-db-update",
            "--offline-scan",
            "--format", "json",
            "--output", output_file,
            repo_dir
        ]

        self.logger.debug(f"Running Trivy command: {' '.join(command)}")

        try:
            result = subprocess.run(
                command,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=Config.DEFAULT_PROCESS_TIMEOUT
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"Trivy scan failed. Return code {result.returncode}: {result.stderr.strip()}"
                )

        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"Trivy scan timed out after {e.timeout} seconds.")

        self.logger.info(f"Trivy scan completed successfully for repo_id: {repo['repo_id']}")

    def parse_trivy_output(self, repo_dir, repo):

        output_file = os.path.join(repo_dir, "trivy_report.json")

        try:
            with open(output_file, "r") as f:
                data = json.load(f)
            self.logger.info(f"Parsed Trivy output successfully for repo_id: {repo['repo_id']}")
            return data

        except FileNotFoundError:
            raise RuntimeError(f"Trivy output file missing in {repo_dir}")

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid Trivy JSON format: {e}")

    def save_trivy_results(self, repo_id, results):

        session = Session()
        try:
            session.query(TrivyVulnerability).filter_by(repo_id=repo_id).delete()
            total_vulnerabilities = 0

            for item in results.get("Results", []):
                target = item.get("Target")
                vulnerabilities = item.get("Vulnerabilities", [])
                resource_class = item.get("Class")
                resource_type = item.get("Type")

                for vuln in vulnerabilities:
                    trivy_vuln = TrivyVulnerability(
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
                    )
                    session.add(trivy_vuln)
                    total_vulnerabilities += 1

            session.commit()
            return total_vulnerabilities

        except Exception as e:
            session.rollback()
            self.logger.error(f"Failed saving Trivy vulnerabilities: {e}")
            raise

        finally:
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
    analyzer = TrivyAnalyzer(run_id="TRIVY_STANDALONE_RUN_001")

    try:
        analyzer.logger.info(f"Starting standalone Trivy analysis for repo_dir: {repo_dir}, repo_id: {repo['repo_id']}")
        result = analyzer.run_analysis(repo_dir, repo=repo)
        analyzer.logger.info(f"Standalone Trivy analysis result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone Trivy analysis: {e}")
    finally:
        session.close()
        analyzer.logger.info(f"Database session closed for repo_id: {repo['repo_id']}")
