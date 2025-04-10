import os
import json
from sqlalchemy.dialects.postgresql import insert
from shared.models import Session, CheckovSummary
from shared.execution_decorator import analyze_execution
from subprocess import run, DEVNULL, TimeoutExpired
from shared.base_logger import BaseLogger
import logging
from config.config import Config

class CheckovAnalyzer(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)

    @analyze_execution(session_factory=Session, stage="Checkov Analysis")
    def run_analysis(self, repo_dir, repo):
        self.logger.info(
            f"Starting Checkov analysis for repo_id: {repo['repo_id']} (repo_slug: {repo['repo_slug']})."
        )
        if not os.path.exists(repo_dir):
            raise FileNotFoundError(f"Repository directory does not exist: {repo_dir}")

        results_file = self._run_checkov_command(repo_dir, repo)
        return self._process_checkov_results(repo, results_file)

    def _run_checkov_command(self, repo_dir, repo):
        output_dir = os.path.join(repo_dir, "checkov_results")
        os.makedirs(output_dir, exist_ok=True)
        error_log_file = os.path.join(output_dir, "checkov_errors.log")

        cmd = [
            "checkov",
            "--directory", repo_dir,
            "--output", "json",
            "--output-file-path", output_dir,
            "--skip-download",
            "--framework",
            "bitbucket_pipelines", "cloudformation", "dockerfile", "github_configuration",
            "gitlab_configuration", "gitlab_ci", "bitbucket_configuration", "helm",
            "json", "yaml", "kubernetes", "kustomize", "openapi", "sca_package",
            "sca_image", "secrets", "serverless", "terraform", "terraform_plan"
        ]

        self.logger.info(f"Checkov command to execute: {' '.join(cmd)}")

        try:
            self.logger.info(f"Executing Checkov command for repo_id: {repo['repo_id']}")
            with open(error_log_file, "w") as error_log:
                run(
                    cmd,
                    check=False,
                    text=True,
                    stdout=DEVNULL,
                    stderr=error_log,
                    timeout=180
                    #timeout=Config.DEFAULT_PROCESS_TIMEOUT
                )
        except TimeoutExpired as e:
            msg = f"Checkov command timed out for repo_id {repo['repo_id']} after {e.timeout} seconds."
            self.logger.error(msg)
            raise RuntimeError(msg) from e
        except Exception as e:
            msg = f"Error executing Checkov command for repo_id: {repo['repo_id']}. Error: {str(e)}"
            self.logger.error(msg)
            raise RuntimeError(msg) from e

        results_file = os.path.join(output_dir, "results_json.json")
        if not os.path.isfile(results_file):
            raise FileNotFoundError(f"Checkov did not produce the expected results file in {output_dir}.")
        message = f"Checkov results successfully produced at: {results_file}"
        self.logger.info(message)
        return results_file


    def _process_checkov_results(self, repo, results_file):
        try:

            self.parse_and_process_checkov_output(repo['repo_id'], results_file)
            with open(results_file, "r") as file:
                return file.read()
        except json.JSONDecodeError as e:
            msg = f"Failed to parse Checkov output for repo_id: {repo['repo_id']}. Error: {str(e)}"
            self.logger.error(msg)
            raise ValueError(msg) from e
        except Exception as e:
            msg = f"Error processing Checkov output for repo_id: {repo['repo_id']}. Error: {str(e)}"
            self.logger.error(msg)
            raise RuntimeError(msg) from e

    def parse_and_process_checkov_output(self, repo_id, checkov_output_path):

        def process_summary(check_type, summary):

            self.save_checkov_results(
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

            elif isinstance(checkov_data, dict):
                process_summary(checkov_data["check_type"], checkov_data["summary"])
                return f"Processed single check type: {checkov_data['check_type']}."

            elif isinstance(checkov_data, list):
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

    def save_checkov_results(self, repo_id, check_type, passed, failed, skipped, parsing_errors, resource_count):

        try:

            session = Session()
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
            raise
        finally:
            session.close()


if __name__ == "__main__":
    repo_slug = "sonar-metrics"
    repo_id = "sonar-metrics"
    repo_dir = "/Users/fadzi/tools/gradle_projects/VyAPI"

    repo = {
        "repo_id": repo_id,
        "repo_slug": repo_slug
    }

    session = Session()
    analyzer = CheckovAnalyzer()

    try:
        analyzer.logger.info(f"Starting standalone Checkov analysis for mock repo_id: {repo['repo_id']}")
        result = analyzer.run_analysis(repo_dir, repo=repo, run_id="STANDALONE_RUN_001")
        analyzer.logger.info(f"Standalone Checkov analysis result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone Checkov analysis: {e}")

