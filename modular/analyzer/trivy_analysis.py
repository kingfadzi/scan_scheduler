import os
import json
import logging
import subprocess
import shutil
from pathlib import Path
from sqlalchemy.dialects.postgresql import insert
from modular.shared.execution_decorator import analyze_execution
from modular.shared.models import Session, TrivyVulnerability
from modular.shared.config import Config
from modular.shared.base_logger import BaseLogger
from modular.shared.sbom_processor import SBOMProcessor


class TrivyAnalyzer(BaseLogger):

    def __init__(self):
        self.logger = self.get_logger("TrivyAnalyzer")
        self.logger.setLevel(logging.WARN)

    @analyze_execution(session_factory=Session, stage="Trivy Analysis")
    def run_analysis(self, repo_dir, repo, session, run_id=None):
        self.logger.info(f"Starting Trivy analysis for repo_id: {repo.repo_id}")

        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        try:
            # Run vulnerability scan
            self.logger.info("Executing vulnerability scan")
            vuln_data = self.run_vulnerability_scan(repo_dir, repo)
            
            # Generate and persist SBOM
            self.logger.info("Generating SBOM")
            sbom_path = self.generate_sbom(repo_dir, repo)
            
            self.logger.info("Persisting SBOM to database")
            SBOMProcessor().persist_dependencies(
                sbom_file=sbom_path,
                repo_id=repo.repo_id
            )

            return json.dumps(vuln_data)

        except Exception as e:
            self.logger.error(f"Analysis failed: {str(e)}")
            raise

    def run_vulnerability_scan(self, repo_dir, repo):
        """Execute Trivy vulnerability scan and return results"""
        try:
            result = subprocess.run(
                ["trivy", "repo", "--skip-db-update", "--skip-java-db-update",
                 "--offline-scan", "--format", "json", repo_dir],
                capture_output=True,
                text=True,
                check=True,
                timeout=Config.DEFAULT_PROCESS_TIMEOUT
            )
            return json.loads(result.stdout.strip())

        except subprocess.TimeoutExpired as e:
            self.handle_error(f"Vulnerability scan timeout: {e.timeout}s", repo.repo_id)
        except subprocess.CalledProcessError as e:
            self.handle_error(f"Vulnerability scan failed: {e.stderr}", repo.repo_id)

    def generate_sbom(self, repo_dir, repo):
        """Generate CycloneDX format SBOM and return file path"""
        sbom_path = os.path.join(repo_dir, f"sbom-{repo.repo_slug}.cdx.json")
        
        try:
            subprocess.run(
                ["trivy", "sbom",
                 "--format", "cyclonedx",
                 "--output", sbom_path, repo_dir],
                capture_output=True,
                text=True,
                check=True,
                timeout=Config.DEFAULT_PROCESS_TIMEOUT
            )
            return sbom_path

        except subprocess.TimeoutExpired as e:
            self.handle_error(f"SBOM generation timeout: {e.timeout}s", repo.repo_id)
        except subprocess.CalledProcessError as e:
            self.handle_error(f"SBOM generation failed: {e.stderr}", repo.repo_id)

    def handle_error(self, message, repo_id):
        """Centralized error handling"""
        error_msg = f"Repo {repo_id} - {message}"
        self.logger.error(error_msg)
        raise RuntimeError(error_msg)

    def prepare_trivyignore(self, repo_dir):
        """Copy .trivyignore template to repository directory"""
        trivyignore_path = os.path.join(repo_dir, ".trivyignore")
        if os.path.exists(trivyignore_path):
            self.logger.info(f".trivyignore already exists in {repo_dir}")
            return
        try:
            shutil.copy(Config.TRIVYIGNORE_TEMPLATE, trivyignore_path)
            self.logger.info(f"Copied .trivyignore to {repo_dir}")
        except Exception as e:
            self.logger.error(f"Error copying .trivyignore: {e}")
            raise

    def save_trivy_results(self, session, repo_id, results):
        """Save vulnerability results to database"""
        self.logger.debug(f"Processing vulnerabilities for repo_id: {repo_id}")
        try:
            total_vulnerabilities = 0
            for item in results.get("Results", []):
                target = item.get("Target")
                vulnerabilities = item.get("Vulnerabilities", [])
                resource_class = item.get("Class")
                resource_type = item.get("Type")

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
            return total_vulnerabilities

        except Exception as e:
            self.logger.exception(f"Error saving vulnerabilities: {e}")
            session.rollback()
            raise

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
        analyzer.logger.info(f"Starting analysis for {repo.repo_slug}")
        result = analyzer.run_analysis(repo_dir, repo=repo, session=session, run_id="STANDALONE_RUN_001")
        analyzer.logger.info(f"Analysis completed successfully")
    except Exception as e:
        analyzer.logger.error(f"Analysis failed: {e}")
    finally:
        session.close()
        analyzer.logger.info("Database session closed")
