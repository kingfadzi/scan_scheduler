import logging
from prefect import flow, task, get_run_logger
from prefect.cache_policies import NO_CACHE
from prefect.context import get_run_context
import asyncio
from datetime import datetime

from modular.analyzer.dependency_analysis import DependencyAnalyzer
from modular.analyzer.kantra_analysis import KantraAnalyzer
from modular.shared.models import Session
from modular.shared.utils import refresh_views, create_batches
from modular.shared.tasks import clone_repository_task, cleanup_repo_task, update_status_task

@flow(name="component_patterns_flow")
async def component_patterns_flow(payload: dict):
    logger = get_run_logger()
    logger.info("[Component Patterns] Starting component_patterns_flow")

    batches = create_batches(payload, batch_size=1000, num_partitions=10)
    all_repos = [repo for batch in batches for repo in batch]
    logger.info(f"[Component Patterns] Processing {len(all_repos)} repositories.")

    run_ctx = get_run_context()
    run_id = str(run_ctx.flow_run.id) if run_ctx and run_ctx.flow_run else "default_run_id"

    tasks = [asyncio.to_thread(component_patterns_repo_processing_flow, repo, run_id)
             for repo in all_repos]
    await asyncio.gather(*tasks)

    logger.info("[Component Patterns] All repositories processed. Refreshing views")
    refresh_views()
    logger.info("[Component Patterns] Finished component_patterns_flow")

@flow(name="component_patterns_repo_processing_flow")
def component_patterns_repo_processing_flow(repo, run_id):
    logger = get_run_logger()
    with Session() as session:
        attached_repo = session.merge(repo)
        repo_dir = None
        try:
            logger.info(f"[Component Patterns] Processing repository: {attached_repo.repo_id}")
            repo_dir = clone_repository_task(attached_repo, run_id, "analyze_components")
            run_dependency_analysis(repo_dir, attached_repo, session, run_id)
            run_kantra_analysis(repo_dir, attached_repo, session, run_id)
        except Exception as e:
            logger.error(f"[Component Patterns] Error processing repository {attached_repo.repo_id}: {e}")
            attached_repo.status = "ERROR"
            attached_repo.comment = str(e)
            attached_repo.updated_on = datetime.utcnow()
            session.add(attached_repo)
            session.commit()
        finally:
            if repo_dir:
                cleanup_repo_task(repo_dir)
        update_status_task(attached_repo, run_id, session)

@task(cache_policy=NO_CACHE)
def run_dependency_analysis(repo_dir, repo, session, run_id):
    logger = get_run_logger()
    logger.info(f"[Component Patterns] Starting Dependency analysis for repository: {repo.repo_id}")
    analyzer = DependencyAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        session=session,
        run_id=run_id
    )
    logger.info(f"[Component Patterns] Completed Dependency analysis for repository: {repo.repo_id}")

@task(cache_policy=NO_CACHE)
def run_kantra_analysis(repo_dir, repo, session, run_id):
    logger = get_run_logger()
    logger.info(f"[Component Patterns] Starting Kantra analysis for repository: {repo.repo_id}")
    analyzer = KantraAnalyzer(logger=logger)
    analyzer.run_analysis(
        repo_dir=repo_dir,
        repo=repo,
        session=session,
        run_id=run_id
    )
    logger.info(f"[Component Patterns] Completed Kantra analysis for repository: {repo.repo_id}")

if __name__ == "__main__":
    import asyncio
    example_payload = {
        "payload": {
            "host_name": ["github.com"],
            "activity_status": ["ACTIVE"],
            "main_language": ["Python"]
        }
    }
    asyncio.run(component_patterns_flow(payload=example_payload))
