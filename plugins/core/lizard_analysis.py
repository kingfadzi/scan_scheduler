import subprocess
import logging
import os
from sqlalchemy.dialects.postgresql import insert
from shared.models import Session, LizardSummary
from shared.execution_decorator import analyze_execution
from shared.base_logger import BaseLogger
import csv
import io
from config.config import Config

class LizardAnalyzer(BaseLogger):

    def __init__(self, logger=None):
        if logger is None:
            self.logger = self.get_logger("LizardAnalyzer")
        else:
            self.logger = logger
        self.logger.setLevel(logging.INFO)

    def _read_analysis_file(self, analysis_file, repo):
        try:
            with open(analysis_file, "r") as infile:
                file_contents = infile.read()
        except Exception as e:
            error_message = f"Error reading analysis file {analysis_file} for repository {repo['repo_name']}: {e}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)
        return file_contents

    @analyze_execution(session_factory=Session, stage="Lizard Analysis")
    def run_analysis(self, repo_dir, repo):
        self.logger.info(f"Starting lizard analysis for repo_id: {repo['repo_id']} (repo_slug: {repo['repo_slug']})")
        analysis_file = os.path.join(repo_dir, "analysis.txt")

        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        self.logger.debug(f"Repository directory found: {repo_dir}")
        self.logger.info(f"Executing lizard command in directory: {repo_dir}")
        try:
            with open(analysis_file, "w") as outfile:
                subprocess.run(
                    ["lizard", "--csv"],
                    stdout=outfile,
                    stderr=subprocess.DEVNULL,
                    check=True,
                    cwd=repo_dir,
                    timeout=Config.DEFAULT_PROCESS_TIMEOUT
                )
            self.logger.info(f"Lizard analysis completed successfully. Output file: {analysis_file}")

        except subprocess.TimeoutExpired as e:
            error_message = f"Lizard command timed out for repo_id {repo['repo_id']} after {e.timeout} seconds."
            self.logger.error(error_message)
            raise RuntimeError(error_message)


        except subprocess.CalledProcessError as e:
            error_message = f"Lizard command failed for repo_id {repo['repo_id']}: {e.stderr.decode().strip()}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        if not os.path.exists(analysis_file):
            error_message = f"Language analysis file not found for repository {repo['repo_name']}. Expected at: {analysis_file}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        self.logger.info(f"Parsing lizard output for repo_id: {repo['repo_id']}")
        try:
            processed_metrics = self.parse_and_persist_lizard_results(repo['repo_id'], analysis_file)
        except Exception as e:
            error_message = f"Error while parsing or saving analysis results for repository {repo['repo_name']}: {e}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        return self._read_analysis_file(analysis_file, repo)

    def parse_and_persist_lizard_results(self, repo_id, analysis_file_path):
        summary = {
            "total_nloc": 0,
            "total_ccn": 0,
            "total_token_count": 0,
            "function_count": 0,
            "avg_ccn": 0.0
        }

        expected_column_count = 11

        try:
            self.logger.info(f"Reading lizard analysis file at: {analysis_file_path}")

            with open(analysis_file_path, 'r') as f:
                file_contents = f.read()
            self.logger.debug(f"File contents:\n{file_contents}")

            valid_lines = []
            for line in file_contents.split('\n'):
                if line.count(',') == expected_column_count - 1:
                    valid_lines.append(line)

            if not valid_lines:
                self.logger.warn("No valid data lines found in the file.")
                return

            self.logger.debug(f"Valid lines extracted:\n" + "\n".join(valid_lines))

            csv_file = io.StringIO("\n".join(valid_lines))
            reader = csv.DictReader(csv_file, fieldnames=[
                "nloc", "ccn", "token_count", "param", "function_length", "location",
                "file_name", "function_name", "long_name", "start_line", "end_line"
            ])

            for row_number, row in enumerate(reader, start=1):

                if not all([row["nloc"], row["ccn"], row["token_count"]]):
                    raise ValueError(f"Invalid data in row {row_number}: {row}")

                try:
                    nloc = int(row["nloc"])
                    ccn = int(row["ccn"])
                    token_count = int(row["token_count"])
                except ValueError as ve:
                    raise ValueError(f"Value conversion error in row {row_number}: {row} - {ve}")

                summary["total_nloc"] += nloc
                summary["total_ccn"] += ccn
                summary["total_token_count"] += token_count
                summary["function_count"] += 1

            if summary["function_count"] == 0:
                raise ValueError("No valid functions found in the analysis file.")

            summary["avg_ccn"] = summary["total_ccn"] / summary["function_count"]

            self.logger.info(f"Summary for repo_id {repo_id}: "
                             f"Total NLOC: {summary['total_nloc']}, Avg CCN: {summary['avg_ccn']}, "
                             f"Total Tokens: {summary['total_token_count']}, Function Count: {summary['function_count']}")

            self.save_lizard_summary(repo_id, summary)
            return summary

        except Exception as e:
            self.logger.exception(f"Error parsing lizard results for repository ID {repo_id}: {e}")
            raise

    def save_lizard_summary(self, repo_id, summary):

        self.logger.debug(f"Saving lizard summary metrics for repo_id: {repo_id}")

        session = Session()

        try:
            session.execute(
                insert(LizardSummary).values(
                    repo_id=repo_id,
                    total_nloc=summary["total_nloc"],
                    total_ccn=summary["total_ccn"],
                    total_token_count=summary["total_token_count"],
                    function_count=summary["function_count"],
                    avg_ccn=summary["avg_ccn"]
                ).on_conflict_do_update(
                    index_elements=["repo_id"],
                    set_={
                        "total_nloc": summary["total_nloc"],
                        "total_ccn": summary["total_ccn"],
                        "total_token_count": summary["total_token_count"],
                        "function_count": summary["function_count"],
                        "avg_ccn": summary["avg_ccn"]
                    }
                )
            )
            session.commit()
            self.logger.debug(f"Lizard summary metrics committed to the database for repo_id: {repo_id}")
        except Exception as e:
            self.logger.exception(f"Error saving lizard summary metrics for repo_id {repo_id}: {e}")
            raise
        finally:
            session.close()


if __name__ == "__main__":
    repo_slug = "WebGoat"
    repo_id = "WebGoat"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug
            self.repo_name = repo_slug

    repo = MockRepo(repo_id, repo_slug)
    repo_dir = "/Users/fadzi/tools/python_projects/vuln_django_play"
    session = Session()
    analyzer = LizardAnalyzer()

    try:
        analyzer.logger.info(f"Running lizard analysis for hardcoded repo_id: {repo['repo_id']}, repo_slug: {repo['repo_slug']}")
        result = analyzer.run_analysis(repo_dir, repo=repo)
        analyzer.logger.info(f"Standalone lizard analysis result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone lizard analysis: {e}")
    finally:
        session.close()
        analyzer.logger.info(f"Database session closed for repo_id: {repo['repo_id']}")
