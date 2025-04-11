import os
import subprocess
import logging
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import insert
from shared.models import Session, GoEnryAnalysis
from shared.execution_decorator import analyze_execution
from shared.base_logger import BaseLogger
from config.config import Config

class GoEnryAnalyzer(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)


    @analyze_execution(session_factory=Session, stage="Go Enry Analysis")
    def run_analysis(self, repo_dir, repo):
        self.logger.info(f"Starting language analysis for repository: {repo['repo_name']} (ID: {repo['repo_id']})")
        analysis_file = os.path.join(repo_dir, "analysis.txt")
        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)
        else:
            self.logger.debug(f"Repository directory found: {repo_dir}")
        self.logger.info(f"Running go-enry in directory: {repo_dir}")
        try:
            with open(analysis_file, "w") as outfile:
                subprocess.run(
                    ["go-enry"],
                    stdout=outfile,
                    stderr=subprocess.PIPE,
                    check=True,
                    cwd=repo_dir,
                    timeout=Config.DEFAULT_PROCESS_TIMEOUT
                )
            self.logger.info(f"Language analysis completed successfully. Output file: {analysis_file}")

        except subprocess.TimeoutExpired as e:
            error_message = f"go-enry command timed out for repo_id {repo['repo_id']} after {e.timeout} seconds."
            self.logger.error(error_message)
            raise RuntimeError(error_message)


        except subprocess.CalledProcessError as e:
            error_message = f"Error running go-enry for repository {repo['repo_name']}: {e.stderr.decode().strip()}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)
        if not os.path.exists(analysis_file):
            error_message = f"Language analysis file not found for repository {repo['repo_name']}. Expected at: {analysis_file}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)
        self.logger.info(f"Parsing language analysis results from file: {analysis_file}")
        try:
            self.parse_and_persist_enry_results(repo['repo_id'], analysis_file)
        except Exception as e:
            error_message = f"Error while parsing or saving analysis results for repository {repo['repo_name']}: {e}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)
        return self._read_analysis_file(analysis_file, repo)

    def _read_analysis_file(self, analysis_file, repo):
        try:
            with open(analysis_file, "r") as infile:
                file_contents = infile.read()
        except Exception as e:
            error_message = f"Error reading analysis file {analysis_file} for repository {repo['repo_name']}: {e}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)
        return file_contents

    def parse_and_persist_enry_results(self, repo_id, analysis_file_path):

        try:
            self.logger.info(f"Reading analysis file at: {analysis_file_path}")
            with open(analysis_file_path, "r") as f:
                processed_languages = 0
                for line in f:
                    parts = line.strip().split(maxsplit=1)
                    if len(parts) == 2:
                        percent_usage, language = parts
                        try:
                            percent_usage = float(percent_usage.strip('%'))
                        except ValueError:
                            self.logger.warning(f"Invalid percentage format for language '{language}': {percent_usage}")
                            continue

                        self.logger.debug(f"Parsed result - Language: {language}, Usage: {percent_usage}%")

                        self.save_goenry_analysis( repo_id=repo_id,
                                                   language=language.strip(),
                                                   percent_usage=percent_usage)

                        processed_languages += 1

            self.logger.info(f"Language analysis results saved to the database for repo_id: {repo_id}")
            return processed_languages
        except Exception as e:
            self.logger.exception(f"Error while parsing or saving analysis results for repository ID {repo_id}: {e}")
            raise
        finally:
            session.close()

    def save_goenry_analysis(self, repo_id, language, percent_usage):
        session = Session()
        try:
            session.query(GoEnryAnalysis).filter(
                GoEnryAnalysis.repo_id == repo_id,
                GoEnryAnalysis.language == language.strip()
            ).delete()

            session.add(
                GoEnryAnalysis(
                    repo_id=repo_id,
                    language=language.strip(),
                    percent_usage=percent_usage,
                    analysis_date=datetime.now(timezone.utc)
                )
            )

            session.commit()
            self.logger.info(f"GoEnry analysis saved for repo_id: {repo_id}, language: {language.strip()}")
        except Exception as e:
            session.rollback()
            self.logger.exception(f"Error saving GoEnry analysis for repo_id {repo_id}, language {language.strip()}")
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
    analyzer = GoEnryAnalyzer(run_id="STANDALONE_RUN_ID_001")

    try:
        analyzer.logger.info(f"Running language analysis for repo_dir: {repo_dir}, repo_id: {repo['repo_id']}")
        result = analyzer.run_analysis(repo_dir, repo=repo)
        analyzer.logger.info(f"Standalone language analysis result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone language analysis execution: {e}")
    finally:
        session.close()
        analyzer.logger.info("Session closed.")

