import os
import subprocess
import json
from sqlalchemy.dialects.postgresql import insert
from shared.models import Session, ClocMetric
from shared.execution_decorator import analyze_execution
from shared.base_logger import BaseLogger
import logging
from config.config import Config

class ClocAnalyzer(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)

    @analyze_execution(session_factory=Session, stage="CLOC Analysis")
    def run_analysis(self, repo_dir, repo):

        self.logger.info(f"Starting CLOC analysis for repo_id: {repo['repo_id']} (repo_slug: {repo['repo_slug']}).")

        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        try:
            self.logger.info(f"Executing CLOC command for repo_id: {repo['repo_id']}")
            result = subprocess.run(
                ["cloc", "--vcs=git", "--json", str(repo_dir)],
                capture_output=True,
                text=True,
                check=False,
                timeout=Config.DEFAULT_PROCESS_TIMEOUT
            )

            stdout_str = result.stdout.strip()
            if not stdout_str:
                error_message = f"No output from CLOC command for repo_id: {repo['repo_id']}"
                self.logger.error(error_message)
                raise RuntimeError(error_message)

            self.logger.info(f"Parsing CLOC output for repo_id: {repo['repo_id']}")
            try:
                cloc_data = json.loads(stdout_str)

            except subprocess.TimeoutExpired as e:
                error_message = f"CLOC command timed out for repo_id {repo['repo_id']} after {e.timeout} seconds."
                self.logger.error(error_message)
                raise RuntimeError(error_message)
            except json.JSONDecodeError as e:
                error_message = f"Error decoding CLOC JSON output for repo_id {repo['repo_id']}: {e}"
                self.logger.error(error_message)
                raise RuntimeError(error_message)

            self.logger.info(f"Saving CLOC results to the database for repo_id: {repo['repo_id']}")
            processed_languages = self.save_cloc_results(repo['repo_id'], cloc_data)


        except Exception as e:
            self.logger.exception(f"Error during CLOC execution for repo_id {repo['repo_id']}: {e}")
            raise

        return json.dumps(cloc_data)

    def save_cloc_results(self, repo_id, results):
        self.logger.debug(f"Processing CLOC results for repo_id: {repo_id}")
    
        try:
            processed_languages = 0
            session = Session()
    
            for language, metrics in results.items():
                if language == "SUM":
                    self.logger.debug(f"Skipping SUM in CLOC results for repo_id: {repo_id}")
                    continue
    
                self.logger.debug(f"Saving metrics for language: {language} in repo_id: {repo_id}")
    
                session.execute(
                    insert(ClocMetric).values(
                        repo_id=repo_id,
                        language=language,
                        files=metrics["nFiles"],
                        blank=metrics["blank"],
                        comment=metrics["comment"],
                        code=metrics["code"]
                    ).on_conflict_do_update(
                        index_elements=["repo_id", "language"],
                        set_={
                            "files": metrics["nFiles"],
                            "blank": metrics["blank"],
                            "comment": metrics["comment"],
                            "code": metrics["code"],
                        }
                    )
                )
                processed_languages += 1
    
            session.commit()
            self.logger.debug(f"CLOC results committed to the database for repo_id: {repo_id}")
            return processed_languages
    
        except Exception as e:
            self.logger.exception(f"Error saving CLOC results for repo_id {repo_id}")
            raise
        finally:
            session.close()


if __name__ == "__main__":
    repo_slug = "VulnerableLightApp"
    repo_id = "VulnerableLightApp"
    repo_dir = f"/tmp/{repo_slug}"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug

    repo = MockRepo(repo_id, repo_slug)
    session = Session()

    analyzer = ClocAnalyzer()

    try:
        analyzer.logger.info(f"Starting standalone CLOC analysis for mock repo_id: {repo['repo_id']}")
        result = analyzer.run_analysis(repo_dir, repo=repo)
        analyzer.logger.info(f"Standalone CLOC analysis result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone CLOC analysis: {e}")
    finally:
        session.close()
        analyzer.logger.info(f"Database session closed for repo_id: {repo['repo_id']}")
