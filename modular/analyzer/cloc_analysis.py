import os
import subprocess
import json
from sqlalchemy.dialects.postgresql import insert
from modular.shared.models import Session, ClocMetric
from modular.shared.execution_decorator import analyze_execution
from modular.shared.base_logger import BaseLogger
import logging

class ClocAnalyzer(BaseLogger):

    def __init__(self):
        self.logger = self.get_logger("ClocAnalyzer")
        self.logger.setLevel(logging.INFO)

    @analyze_execution(session_factory=Session, stage="CLOC Analysis")
    def run_analysis(self, repo_dir, repo, session, run_id=None):

        self.logger.info(f"Starting CLOC analysis for repo_id: {repo.repo_id} (repo_slug: {repo.repo_slug}).")

        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        try:
            self.logger.info(f"Executing CLOC command for repo_id: {repo.repo_id}")
            result = subprocess.run(
                ["cloc", "--vcs=git", "--json", str(repo_dir)],
                capture_output=True,
                text=True,
                check=False
            )

            stdout_str = result.stdout.strip()
            if not stdout_str:
                error_message = f"No output from CLOC command for repo_id: {repo.repo_id}"
                self.logger.error(error_message)
                raise RuntimeError(error_message)

            self.logger.info(f"Parsing CLOC output for repo_id: {repo.repo_id}")
            try:
                cloc_data = json.loads(stdout_str)
            except json.JSONDecodeError as e:
                error_message = f"Error decoding CLOC JSON output for repo_id {repo.repo_id}: {e}"
                self.logger.error(error_message)
                raise RuntimeError(error_message)

            self.logger.info(f"Saving CLOC results to the database for repo_id: {repo.repo_id}")
            processed_languages = self.save_cloc_results(session, repo.repo_id, cloc_data)

        except Exception as e:
            self.logger.exception(f"Error during CLOC execution for repo_id {repo.repo_id}: {e}")
            raise

        return json.dumps(cloc_data)
        #return f"{processed_languages} languages processed."

    def save_cloc_results(self, session, repo_id, results):

        self.logger.debug(f"Processing CLOC results for repo_id: {repo_id}")

        try:
            processed_languages = 0
            for language, metrics in results.items():
                if language == "header":
                    self.logger.debug(f"Skipping header in CLOC results for repo_id: {repo_id}")
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
        analyzer.logger.info(f"Starting standalone CLOC analysis for mock repo_id: {repo.repo_id}")
        result = analyzer.run_analysis(repo_dir, repo=repo, session=session, run_id="STANDALONE_RUN_001")
        analyzer.logger.info(f"Standalone CLOC analysis result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone CLOC analysis: {e}")
    finally:
        session.close()
        analyzer.logger.info(f"Database session closed for repo_id: {repo.repo_id}")
