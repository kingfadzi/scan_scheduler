from modular.analyzer.cloning import CloningAnalyzer
from modular.shared.utils import determine_final_status
from prefect.cache_policies import NO_CACHE
from modular.shared.utils import refresh_views, create_batches
import asyncio
from prefect import task, get_run_logger
from prefect.context import get_run_context
from modular.shared.models import Session
from datetime import datetime


@task(name="Start Task")
def start_task(flow_prefix: str) -> str:
    logger = get_run_logger()
    logger.info(f"[{flow_prefix}] Starting flow")
    return flow_prefix


@task(name="Create Batches Task")
def create_batches_task(payload: dict, batch_size: int = 10):
    """
    Return a generator that yields small batches of repositories (each <= batch_size).
    Using offset/limit under the hood. We no longer flatten or partition them.
    """
    return create_batches(payload, batch_size)


@task(name="Clone Repository Task", cache_policy=NO_CACHE)
def clone_repository_task(repo, run_id, sub_dir):
    logger = get_run_logger()
    cloning_analyzer = CloningAnalyzer(logger=logger)
    result = cloning_analyzer.clone_repository(repo=repo, run_id=run_id, sub_dir=sub_dir)
    return result


@task(name="Clean Up Repository Task", cache_policy=NO_CACHE)
def cleanup_repo_task(repo_dir):
    logger = get_run_logger()
    cloning_analyzer = CloningAnalyzer(logger=logger)
    cloning_analyzer.cleanup_repository_directory(repo_dir)


@task(name="Update Processing Status Task", cache_policy=NO_CACHE)
def update_status_task(repo, run_id, session):
    determine_final_status(repo, run_id, session)


@task(name="Refresh Views Task")
def refresh_views_task(flow_prefix: str) -> None:
    logger = get_run_logger()
    logger.info(f"[{flow_prefix}] Refreshing views")
    refresh_views()
    logger.info(f"[{flow_prefix}] Views refreshed")


def generate_repo_flow_run_name():
    run_ctx = get_run_context()
    flow_name = run_ctx.flow_run.name
    repo_slug = run_ctx.flow_run.parameters.get("repo_slug")
    return f"{repo_slug}"


def generate_main_flow_run_name():
    run_ctx = get_run_context()
    flow_name = run_ctx.flow_run.name
    start_time = run_ctx.flow_run.expected_start_time
    formatted_time = start_time.strftime('%Y-%m-%d %H:%M:%S')
    return f"{formatted_time}"


async def generic_main_flow(
        payload: dict,
        single_repo_processing_flow,  # A subflow function that processes one repository.
        flow_prefix: str,
        batch_size: int,            # We removed num_partitions
):
    logger = get_run_logger()

    # Step 1: Start the flow.
    start_task(flow_prefix)

    # Step 2: Create a generator that yields batches
    # Instead of returning one giant list, we now stream them.
    repo_batches = create_batches_task(payload, batch_size)
    logger.info(f"[{flow_prefix}] Created repository batch generator (batch_size={batch_size}).")

    # Step 3: Retrieve run_id from Prefect context (or use default if not available).
    run_ctx = get_run_context()
    run_id = str(run_ctx.flow_run.id) if run_ctx and run_ctx.flow_run else "default_run_id"

    # Step 4: For each batch, process the repos concurrently
    batch_index = 0
    # We'll convert the generator from the Prefect task result into an actual Python iterator.
    # Because create_batches_task returns a generator-like object, we can iterate over it.
    for batch in repo_batches:
        batch_index += 1
        logger.info(f"[{flow_prefix}] Processing batch #{batch_index}, with {len(batch)} repos.")

        tasks = [
            asyncio.create_task(
                asyncio.to_thread(
                    single_repo_processing_flow,
                    repo,
                    getattr(repo, "repo_slug", str(repo)),  # Force the slug value now
                    run_id
                )
            )
            for repo in batch
        ]
        await asyncio.gather(*tasks)

    # Step 5: Refresh views after processing all batches.
    refresh_views_task(flow_prefix)
    logger.info(f"[{flow_prefix}] Finished flow")


def generic_single_repo_processing_flow(
        repo,
        run_id,
        sub_tasks: list,
        sub_dir: str,
        flow_prefix: str
):
    """
    (Unchanged) - Only processes a single repo. We haven't altered this at all.
    """
    logger = get_run_logger()
    with Session() as session:
        attached_repo = session.merge(repo)
        repo_dir = None
        try:
            logger.info(f"[{flow_prefix}] Processing repository: {attached_repo.repo_id}")

            repo_dir = clone_repository_task(attached_repo, run_id, sub_dir)

            for task_fn in sub_tasks:
                task_fn(repo_dir, attached_repo, session, run_id)

        except Exception as e:
            logger.error(f"[{flow_prefix}] Error processing repository {attached_repo.repo_id}: {e}")
            attached_repo.status = "ERROR"
            attached_repo.comment = str(e)
            attached_repo.updated_on = datetime.utcnow()
            session.add(attached_repo)
            session.commit()
        finally:
            if repo_dir:
                cleanup_repo_task(repo_dir)
        update_status_task(attached_repo, run_id, session)