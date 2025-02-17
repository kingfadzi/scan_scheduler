import asyncio
from prefect import flow, task, get_run_logger
from prefect.cache_policies import NO_CACHE

from modular.analyzer.trivy_analysis import TrivyAnalyzer
from modular.analyzer.syft_grype_analysis import SyftAndGrypeAnalyzer
from modular.shared.models import Session
from modular.shared.tasks import (
    generic_main_flow,
    generic_single_repo_processing_flow,
    generate_repo_flow_run_name,
    generate_main_flow_run_name
)


@flow(name="Vulnerabilities Main Flow", flow_run_name=generate_main_flow_run_name)
async def vulnerabilities_flow(payload: dict):

    await generic_main_flow(
        payload=payload,
        single_repo_processing_flow=vulnerabilities_repo_processing_flow,
        flow_prefix="Vulnerabilities",
        batch_size=1000,
        num_partitions=5,
    )


@flow(flow_run_name=generate_repo_flow_run_name)
def vulnerabilities_repo_processing_flow(repo, repo_slug, run_id):

    sub_tasks = [
        run_trivy_analysis_task,
        run_syft_grype_analysis_task
    ]

    generic_single_repo_processing_flow(
        repo=repo,
        run_id=run_id,
        sub_tasks=sub_tasks,
        sub_dir="analyze_vulnerabilities",
        flow_prefix="Vulnerabilities"
    )


@task(name="Run Trivy Analysis Task", cache_policy=NO_CACHE)
def run_trivy_analysis_task(repo_dir, repo, session, run_id):

    logger = get_run_logger()
    logger.info(f"[Vulnerabilities] Starting Trivy analysis for repository: {repo.repo_id}")

    analyzer = TrivyAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        session=session,
        run_id=run_id
    )

    logger.info(f"[Vulnerabilities] Completed Trivy analysis for repository: {repo.repo_id}")


@task(name="Run Syft+Grype Analysis Task", cache_policy=NO_CACHE)
def run_syft_grype_analysis_task(repo_dir, repo, session, run_id):

    logger = get_run_logger()
    logger.info(f"[Vulnerabilities] Starting Syft+Grype analysis for repository: {repo.repo_id}")

    analyzer = SyftAndGrypeAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        session=session,
        run_id=run_id
    )

    logger.info(f"[Vulnerabilities] Completed Syft+Grype analysis for repository: {repo.repo_id}")


if __name__ == "__main__":
    example_payload = {
        "payload": {
            "host_name": ["github.com"],
            "activity_status": ["ACTIVE"],
            "main_language": ["Python"]
        }
    }
    asyncio.run(vulnerabilities_flow(payload=example_payload))
