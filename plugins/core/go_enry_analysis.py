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

        session = Session()

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

                        session.execute(
                            insert(GoEnryAnalysis).values(
                                repo_id=repo_id,
                                language=language.strip(),
                                percent_usage=percent_usage,
                                analysis_date=datetime.now(timezone.utc)
                            ).on_conflict_do_update(
                                index_elements=['repo_id', 'language'],
                                set_={
                                    'percent_usage': percent_usage,
                                    'analysis_date': datetime.now(timezone.utc)
                                }
                            )
                        )
                        processed_languages += 1
            session.commit()
            self.logger.info(f"Language analysis results saved to the database for repo_id: {repo_id}")
            return processed_languages
        except Exception as e:
            self.logger.exception(f"Error while parsing or saving analysis results for repository ID {repo_id}: {e}")
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
    repo_dir = f"/tmp/{repo['repo_slug']}"
    session = Session()

    analyzer = GoEnryAnalyzer()

    try:
        analyzer.logger.info(f"Running language analysis for hardcoded repo_id: {repo['repo_id']}, repo_slug: {repo['repo_slug']}")
        result = analyzer.run_analysis(repo_dir, repo=repo)
        analyzer.logger.info(f"Standalone language analysis result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone language analysis execution: {e}")
    finally:
        session.close()
        analyzer.logger.info("Session closed.")
