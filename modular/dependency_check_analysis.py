import subprocess
import csv
import logging
import os
import json
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import insert
from modular.models import Session, DependencyCheckResult
from modular.execution_decorator import analyze_execution  # Updated import

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

SYFT_CONFIG_PATH = "/root/.syft/config.yaml"
GRYPE_CONFIG_PATH = "/root/.grype/config.yaml"

@analyze_execution(session_factory=Session, stage="Dependency-Check Analysis")
def run_dependency_check(repo_dir, repo, session, run_id=None):
    """
    Run OWASP Dependency-Check on the given repo_dir and persist results to the database.
    Writes a log file and report to the specified repository directory.

    :param repo_dir: Directory path of the repository to be analyzed.
    :param repo: Repository object containing metadata like repo_id and repo_slug.
    :param session: Database session to persist the results.
    :param run_id: DAG run ID passed for tracking.
    :return: Success message with the number of vulnerabilities processed or raises an exception on failure.
    """
    logger.info(f"Starting Dependency-Check analysis for repo_id: {repo.repo_id} "
                f"(repo_slug: {repo.repo_slug}).")

    # Validate repository directory
    if not os.path.exists(repo_dir):
        error_message = f"Repository directory does not exist: {repo_dir}"
        logger.error(error_message)
        raise FileNotFoundError(error_message)

    logger.debug(f"Repository directory found: {repo_dir}")

    # Paths for Dependency-Check properties, outputs, and logs
    property_file = "/opt/dependency-check/dependency-check.properties"
    retire_js_url = "file:///opt/dependency-check/data/jsrepository.json"
    report_file = os.path.join(repo_dir, "dependency-check-report.json")
    log_file = os.path.join(repo_dir, "dependency-check.log")
    dependency_check_executable = "/opt/dependency-check/bin/dependency-check.sh"

    # Execute the Dependency-Check command
    logger.info(f"Executing Dependency-Check command in directory: {repo_dir}")
    try:
        subprocess.run(
            [
                dependency_check_executable,
                "--scan", repo_dir,
                "--format", "JSON",
                "--propertyfile", property_file,
                "--retireJsUrl", retire_js_url,
                "--noupdate",
                "--disableOssIndex",
                "--project", repo.repo_slug,
                "--log", log_file,  # Write logs to the specified file
                "--out", report_file  # Write the report to the repo directory
            ],
            capture_output=True,
            text=True,
            check=True
        )
        logger.debug(f"Dependency-Check command completed successfully for repo_id: {repo.repo_id}")
    except subprocess.CalledProcessError as e:
        error_message = (f"Dependency-Check command failed for repo_id {repo.repo_id}. "
                         f"Return code: {e.returncode}. Stderr: {e.stderr.strip()}")
        logger.error(error_message)
        logger.debug("Full exception info:", exc_info=True)
        raise RuntimeError("Dependency-Check analysis failed.") from e

    # Check for Dependency-Check report
    if not os.path.exists(report_file):
        error_message = f"Dependency-Check did not produce the expected report: {report_file}"
        logger.error(error_message)
        raise RuntimeError("Dependency-Check analysis did not generate a report.")

    logger.info(f"Dependency-Check report found at: {report_file}")

    # Parse the report and persist results
    logger.info(f"Parsing Dependency-Check report for repo_id: {repo.repo_id}")
    try:
        processed_vulnerabilities = parse_dependency_check_report(report_file, repo, session)
    except Exception as e:
        error_message = f"Error while parsing or saving Dependency-Check results for repository {repo.repo_name}: {e}"
        logger.error(error_message)
        raise RuntimeError(error_message)

    # Return a comprehensive success message
    return (
        f"{processed_vulnerabilities} vulnerabilities processed, "
        f"analysis saved successfully."
    )

def parse_dependency_check_report(report_file, repo, session):
    """
    Parse the JSON report from OWASP Dependency-Check and save results to the database.

    :param report_file: Path to the Dependency-Check analysis output file.
    :param repo: Repository object containing metadata like repo_id and repo_slug.
    :param session: Database session for saving results.
    :return: Number of vulnerabilities processed.
    """
    try:
        logger.info(f"Reading Dependency-Check report from: {report_file}")

        # Load the JSON report
        with open(report_file, "r") as file:
            report = json.load(file)

        # Debug: Check top-level keys in the JSON
        logger.debug(f"Top-level keys in the report: {list(report.keys())}")

        # Extract dependencies
        dependencies = report.get("dependencies", [])
        if not dependencies:
            logger.info(f"No dependencies found in Dependency-Check report for repo_id: {repo.repo_id}")
            return 0

        logger.debug(f"Found {len(dependencies)} dependencies in the report for repo_id: {repo.repo_id}")

        # Initialize a counter for processed vulnerabilities
        processed_vulnerabilities = 0

        # Iterate over each dependency
        for dependency in dependencies:
            file_name = dependency.get("fileName", "Unknown")
            file_path = dependency.get("filePath", "Unknown")
            logger.debug(f"Processing dependency - FileName: {file_name}, FilePath: {file_path}")

            vulnerabilities = dependency.get("vulnerabilities", [])
            if not vulnerabilities:
                logger.info(f"No vulnerabilities found for dependency: {file_name}")
                continue

            logger.debug(f"Found {len(vulnerabilities)} vulnerabilities for dependency: {file_name}")

            # Process each vulnerability
            for vulnerability in vulnerabilities:
                logger.debug(f"Processing vulnerability: {vulnerability.get('name')} for file: {file_name}")

                # Extract vulnerability details
                cve = vulnerability.get("name", "No CVE")
                description = vulnerability.get("description", "No description provided")
                severity = vulnerability.get("severity", "UNKNOWN")
                vulnerable_software = vulnerability.get("vulnerableSoftware", [])

                # Serialize vulnerable_software as a JSON string
                serialized_software = json.dumps(vulnerable_software)

                # Save the vulnerability to the database
                session.execute(
                    insert(DependencyCheckResult).values(
                        repo_id=repo.repo_id,
                        cve=cve,
                        description=description,
                        severity=severity,
                        vulnerable_software=serialized_software,
                        analysis_date=datetime.now(timezone.utc)
                    ).on_conflict_do_update(
                        index_elements=["repo_id", "cve"],
                        set_={
                            "description": description,
                            "severity": severity,
                            "vulnerable_software": serialized_software,
                            "analysis_date": datetime.now(timezone.utc)
                        }
                    )
                )
                processed_vulnerabilities += 1

        # Commit the results to the database
        session.commit()
        logger.info(f"Vulnerabilities successfully saved for repo_id: {repo.repo_id}")
        return processed_vulnerabilities

    except Exception as e:
        logger.exception(f"Error while parsing Dependency-Check report for repo_id {repo.repo_id}: {e}")
        raise

if __name__ == "__main__":
    # Hardcoded values for standalone execution
    repo_slug = "WebGoat"  # Changed from "halo" to "WebGoat"
    repo_id = "WebGoat"     # Changed from "halo" to "WebGoat"

    # Mock repo object
    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug
            self.repo_name = repo_slug  # Mock additional attributes if needed

    repo = MockRepo(repo_id, repo_slug)
    repo_dir = f"/tmp/{repo.repo_slug}"  # Changed to match "WebGoat"

    # Create a session and run Dependency-Check analysis
    session = Session()
    try:
        logger.info(f"Starting standalone Dependency-Check analysis for repo_id: {repo.repo_id}")
        # Pass 'repo' as a keyword argument
        result = run_dependency_check(repo_dir, repo=repo, session=session, run_id="STANDALONE_RUN_001")
        logger.info(f"Standalone Dependency-Check analysis result: {result}")
    except Exception as e:
        logger.error(f"Error during standalone Dependency-Check analysis: {e}")
    finally:
        session.close()
        logger.info(f"Database session closed for repo_id: {repo.repo_id}.")
