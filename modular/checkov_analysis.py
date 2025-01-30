import os
import json
from sqlalchemy.dialects.postgresql import insert
from modular.models import Session, CheckovSummary
from modular.execution_decorator import analyze_execution
from subprocess import run, DEVNULL
from modular.base_logger import BaseLogger  # BaseLogger for logging configuration
import logging

class CheckovAnalyzer(BaseLogger):

    def __init__(self):
        self.logger = self.get_logger("CheckovAnalyzer")
        self.logger.setLevel(logging.WARN)  # Set default logging level to WARN

    @analyze_execution(session_factory=Session, stage="Checkov Analysis")
    def run_analysis(self, repo_dir, repo, session, run_id=None):
        self.logger.info(f"Starting Checkov analysis for repo_id: {repo.repo_id} (repo_slug: {repo.repo_slug}).")

        if not os.path.exists(repo_dir):
            raise FileNotFoundError(f"Repository directory does not exist: {repo_dir}")

        output_dir = os.path.join(repo_dir, "checkov_results")
        os.makedirs(output_dir, exist_ok=True)

        # Define log file for errors
        error_log_file = os.path.join(output_dir, "checkov_errors.log")

        try:
            self.logger.info(f"Executing Checkov command for repo_id: {repo.repo_id}")
            with open(error_log_file, "w") as error_log:
                run(
                    [
                        "checkov",
                        "--directory", repo_dir,
                        "--output", "json",
                        "--output-file-path", output_dir,
                        "--skip-download"
                    ],
                    check=False,
                    text=True,
                    stdout=DEVNULL,  # Suppress stdout
                    stderr=error_log  # Redirect stderr to log file
                )

            results_file = os.path.join(output_dir, "results_json.json")
            if not os.path.isfile(results_file):
                raise FileNotFoundError(f"Checkov did not produce the expected results file in {output_dir}.")

            summary = self.parse_and_process_checkov_output(repo.repo_id, results_file, session)

        except Exception as e:
            error_message = f"Error during Checkov execution for repo_id {repo.repo_id}: {e}"
            self.logger.exception(error_message)
            raise RuntimeError(error_message)

        return f"{summary}"

    def parse_and_process_checkov_output(self, repo_id, checkov_output_path, session):
        """
        Parse the Checkov output and process the results.

        :param repo_id: Repository ID being analyzed.
        :param checkov_output_path: Path to the Checkov output JSON file.
        :param session: Database session for saving results.
        :return: A summary string containing processed check types or a general summary.
        """
        def process_summary(check_type, summary):
            """Helper function to save summary data."""
            self.save_checkov_results(
                session,
                repo_id,
                check_type=check_type,
                passed=summary.get("passed", 0),
                failed=summary.get("failed", 0),
                skipped=summary.get("skipped", 0),
                parsing_errors=summary.get("parsing_errors", 0),
                resource_count=summary.get("resource_count", 0),
            )

        try:
            self.logger.info(f"Reading Checkov output file at: {checkov_output_path}")
            with open(checkov_output_path, "r") as file:
                checkov_data = json.load(file)

            if not checkov_data:
                raise ValueError(f"Checkov output is empty for repo_id {repo_id}.")

            self.logger.info(f"Checkov output successfully parsed for repo_id: {repo_id}.")

            if isinstance(checkov_data, dict) and "check_type" not in checkov_data:  # No IaC components found
                process_summary("no-checks", checkov_data)
                return "No IaC components found. Summary saved."

            elif isinstance(checkov_data, dict):  # One check performed
                process_summary(checkov_data["check_type"], checkov_data["summary"])
                return f"Processed single check type: {checkov_data['check_type']}."

            elif isinstance(checkov_data, list):  # Multiple checks performed
                check_types = []
                for check in checkov_data:
                    process_summary(check["check_type"], check["summary"])
                    check_types.append(check["check_type"])
                return f"Processed multiple check types: {', '.join(check_types)}."

            else:
                raise ValueError(f"Unexpected format in Checkov output for repo_id {repo_id}.")

        except (json.JSONDecodeError, ValueError) as e:
            self.logger.error(f"Error parsing Checkov JSON output for repo_id {repo_id}: {e}")
            raise RuntimeError(f"Failed to parse Checkov output for repo_id {repo_id}.") from e

        except Exception as e:
            self.logger.exception(f"Unexpected error processing Checkov output for repo_id {repo_id}: {e}")
            raise RuntimeError(f"Unexpected error processing Checkov output for repo_id {repo_id}.") from e

    def save_checkov_results(self, session, repo_id, check_type, passed, failed, skipped, parsing_errors, resource_count):
        """
        Save Checkov results to the database in CheckovSummary table.
        """
        try:
            # Save summary to CheckovSummary
            session.execute(
                insert(CheckovSummary).values(
                    repo_id=repo_id,
                    check_type=check_type,
                    passed=passed,
                    failed=failed,
                    skipped=skipped,
                    parsing_errors=parsing_errors,
                    resource_count=resource_count,
                ).on_conflict_do_update(
                    index_elements=["repo_id", "check_type"],
                    set_={
                        "passed": passed,
                        "failed": failed,
                        "skipped": skipped,
                        "parsing_errors": parsing_errors,
                        "resource_count": resource_count,
                    },
                )
            )

            session.commit()
            self.logger.info(f"Checkov summary for {check_type} committed to the database for repo_id: {repo_id}")

        except Exception as e:
            self.logger.exception(f"Error saving Checkov summary for repo_id {repo_id}, check_type {check_type}")
            raise  # Raise exception if saving results fails


if __name__ == "__main__":
    repo_slug = "sonar-metrics"
    repo_id = "sonar-metrics"
    repo_dir = f"/tmp/WebGoat"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug

    # Create a mock repo object
    repo = MockRepo(repo_id=repo_id, repo_slug=repo_slug)

    # Initialize a database session
    session = Session()

    analyzer = CheckovAnalyzer()

    try:
        analyzer.logger.info(f"Starting standalone Checkov analysis for mock repo_id: {repo.repo_id}")
        # Explicitly pass the repo object
        result = analyzer.run_analysis(repo_dir, repo=repo, session=session, run_id="STANDALONE_RUN_001")
        analyzer.logger.info(f"Standalone Checkov analysis result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone Checkov analysis: {e}")
