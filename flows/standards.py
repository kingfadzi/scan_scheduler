import asyncio
from prefect import flow, task, get_run_logger
from prefect.cache_policies import NO_CACHE

from modular.analyzer.checkov_analysis import CheckovAnalyzer
from modular.analyzer.semgrep_analysis import SemgrepAnalyzer
from modular.shared.models import Session
from modular.shared.tasks import (
    generic_main_flow,
    generic_single_repo_processing_flow
)
from modular.shared.utils import generate_repo_flow_run_name, generate_main_flow_run_name


@flow(flow_run_name=generate_main_flow_run_name)
async def standards_assessment_flow(payload: dict):

    await generic_main_flow(
        payload=payload,
        single_repo_processing_flow=standards_assessment_repo_processing_flow,
        flow_prefix="Standards Assessment",
        batch_size=1000,
        num_partitions=10,
        concurrency_limit=10
    )


@flow(flow_run_name=generate_repo_flow_run_name)
def standards_assessment_repo_processing_flow(repo, repo_slug, run_id):

    sub_tasks = [
        run_checkov_analysis_task,
        run_semgrep_analysis_task
    ]

    generic_single_repo_processing_flow(
        repo=repo,
        run_id=run_id,
        sub_tasks=sub_tasks,
        sub_dir="analyze_standards",
        flow_prefix="Standards Assessment"
    )


@task(name="Run Checkov Analysis Task", cache_policy=NO_CACHE)
def run_checkov_analysis_task(repo_dir, repo, session, run_id):

    logger = get_run_logger()
    logger.info(f"[Standards Assessment] Starting Checkov analysis for repository: {repo.repo_id}")

    analyzer = CheckovAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        session=session,
        run_id=run_id
    )

    logger.info(f"[Standards Assessment] Completed Checkov analysis for repository: {repo.repo_id}")


@task(name="Run Semgrep Analysis Task", cache_policy=NO_CACHE)
def run_semgrep_analysis_task(repo_dir, repo, session, run_id):

    logger = get_run_logger()
    logger.info(f"[Standards Assessment] Starting Semgrep analysis for repository: {repo.repo_id}")

    analyzer = SemgrepAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        session=session,
        run_id=run_id
    )

    logger.info(f"[Standards Assessment] Completed Semgrep analysis for repository: {repo.repo_id}")


if __name__ == "__main__":
    example_payload = {
        "payload": {
            "host_name": ["github.com"],
            "activity_status": ["ACTIVE"],
            "main_language": ["Python"]
        }
    }
    asyncio.run(standards_assessment_flow(payload=example_payload))
