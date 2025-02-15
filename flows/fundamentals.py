import logging
from prefect import flow, task, get_run_logger
from prefect.tasks import task_input_hash
from prefect.cache_policies import NO_CACHE
from prefect.context import get_run_context

from modular.analyzer.gitlog_analysis import GitLogAnalyzer
from modular.analyzer.go_enry_analysis import GoEnryAnalyzer
from modular.analyzer.lizard_analysis import LizardAnalyzer
from modular.analyzer.cloc_analysis import ClocAnalyzer

from modular.shared.models import Session, Repository
from modular.shared.utils import create_batches, execute_sql_script
from modular.shared.tasks import clone_repository_task, cleanup_repo_task, update_status_task
from modular.shared.base_logger import BaseLogger
from datetime import datetime
import asyncio

class FundamentalsFlow(BaseLogger):

    def __init__(self):
        self.logger = self.get_logger("FundamentalsFlow")
        self.logger.setLevel(logging.WARN)

    @flow(name="run_fundamentals")
    def run_fundamentals(payload: dict):
        instance = FundamentalsFlow()
        instance.orchestrate_flow(payload=payload)

    @flow(name="orchestrate_processing_flow")
    async def orchestrate_flow(self, payload: dict):
        logger = get_run_logger()

        batches = create_batches(payload, batch_size=1000, num_partitions=5)
        all_repos = [repo for batch in batches for repo in batch]
        logger.info(f"Processing {len(all_repos)} repositories.")

        run_ctx = get_run_context()
        run_id = run_ctx.flow_run.id if run_ctx and run_ctx.flow_run else None
        run_id = str(run_id) if run_id else None

        # Run process_repo concurrently in separate threads
        tasks = [asyncio.to_thread(self.process_repo, repo, run_id) for repo in all_repos]
        await asyncio.gather(*tasks)

        logger.info("All repositories processed. Executing SQL script: refresh_views.sql")
        self.execute_sql_script_task("refresh_views.sql")

    @flow(name="Process Repo Flow")
    def process_repo(self, repo, run_id):
        logger_flow = get_run_logger()
        with Session() as session:
            attached_repo = session.merge(repo)
            repo_dir = None
            try:
                logger_flow.info(
                    f"Processing repository: {attached_repo.repo_name} (ID: {attached_repo.repo_id})"
                )
                sub_dir = "analyze_fundamentals"
                repo_dir = clone_repository_task(attached_repo, run_id, sub_dir)
                logger_flow.debug(f"Repository cloned to: {repo_dir}")

                self.run_lizard_task(repo_dir, attached_repo, session, run_id)
                self.run_cloc_task(repo_dir, attached_repo, session, run_id)
                self.run_goenry_task(repo_dir, attached_repo, session, run_id)
                self.run_gitlog_task(repo_dir, attached_repo, session, run_id)
            except Exception as e:
                logger_flow.error(f"Error processing repository {attached_repo.repo_name}: {e}")
                attached_repo.status = "ERROR"
                attached_repo.comment = str(e)
                attached_repo.updated_on = datetime.utcnow()
                session.add(attached_repo)
                session.commit()
            finally:
                if repo_dir:
                    cleanup_repo_task(repo_dir)
                    logger_flow.debug(f"Cleaned up repository directory: {repo_dir}")

            update_status_task(attached_repo, run_id, session)

    @task(cache_policy=NO_CACHE)
    def run_lizard_task(self, repo_dir, repo, session, run_id):
        logger = get_run_logger()
        logger.info(f"Starting Lizard analysis for repository {repo.repo_name} (ID: {repo.repo_id})")
        analyzer = LizardAnalyzer(logger=logger)
        analyzer.run_analysis(
            repo_dir=repo_dir,
            repo=repo,
            session=session,
            run_id=run_id
        )
        logger.info(f"Completed Lizard analysis for repository {repo.repo_name}")

    @task(cache_policy=NO_CACHE)
    def run_cloc_task(self, repo_dir, repo, session, run_id):
        logger = get_run_logger()
        logger.info(f"Starting Cloc analysis for repository {repo.repo_name} (ID: {repo.repo_id})")
        analyzer = ClocAnalyzer(logger=logger)
        analyzer.run_analysis(
            repo_dir=repo_dir,
            repo=repo,
            session=session,
            run_id=run_id
        )
        logger.info(f"Completed Cloc analysis for repository {repo.repo_name}")

    @task(cache_policy=NO_CACHE)
    def run_goenry_task(self, repo_dir, repo, session, run_id):
        logger = get_run_logger()
        logger.info(f"Starting GoEnry analysis for repository {repo.repo_name} (ID: {repo.repo_id})")
        analyzer = GoEnryAnalyzer(logger=logger)
        analyzer.run_analysis(
            repo_dir=repo_dir,
            repo=repo,
            session=session,
            run_id=run_id
        )
        logger.info(f"Completed GoEnry analysis for repository {repo.repo_name}")

    @task(cache_policy=NO_CACHE)
    def run_gitlog_task(self, repo_dir, repo, session, run_id):
        logger = get_run_logger()
        logger.info(f"Starting GitLog analysis for repository {repo.repo_name} (ID: {repo.repo_id})")
        analyzer = GitLogAnalyzer(logger=logger)
        analyzer.run_analysis(
            repo_dir=repo_dir,
            repo=repo,
            session=session,
            run_id=run_id
        )
        logger.info(f"Completed GitLog analysis for repository {repo.repo_name}")

    @task(cache_policy=NO_CACHE)
    def execute_sql_script_task(self, script_name: str):
        execute_sql_script(script_name)

if __name__ == "__main__":
    import asyncio
    flow = FundamentalsFlow()
    example_payload = {
        'host_name': ['github.com'],
        'activity_status': ['ACTIVE'],
        'main_language': ['Python'],
    }
    asyncio.run(flow.orchestrate_flow(payload=example_payload))

