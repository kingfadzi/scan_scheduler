from modular.analyzer.cloning import CloningAnalyzer
from modular.shared.utils import determine_final_status
from prefect.cache_policies import NO_CACHE
from modular.shared.utils import refresh_views, create_batches
import asyncio
from prefect import task, get_run_logger
from prefect.context import get_run_context
from modular.shared.models import Session
from datetime import datetime
from modular.shared.utils import generate_repo_flow_run_name


@task(name="Start Task")
def start_task(flow_prefix: str) -> str:
    logger = get_run_logger()
    logger.info(f"[{flow_prefix}] Starting flow")
    return flow_prefix


@task(name="Create Batches Task")
def create_batches_task(payload: dict, batch_size: int = 1000, num_partitions: int = 10) -> list:
    batches = create_batches(payload, batch_size, num_partitions)
    all_repos = [repo for batch in batches for repo in batch]
    return all_repos


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

@task(name="Syft Analysis Task", cache_policy=NO_CACHE)
def syft_analysis_task(repo_dir):
    logger = get_run_logger()
    syft_analyzer = SyftAnalyzer(logger=logger)
    result = syft_analyzer.run_analysis(repo_dir)
    return result

async def worker(queue, run_id, single_repo_processing_flow):
    """Worker task: continuously process repositories from the queue."""
    while True:
        repo = await queue.get()  # Wait for a repo to process.
        try:
            # Process the repository in a separate thread.
            await asyncio.to_thread(
                single_repo_processing_flow,
                repo,
                getattr(repo, "repo_slug", str(repo)),  # Ensure we have the repo slug.
                run_id
            )
        finally:
            queue.task_done()  # Mark this repo as done.

async def generic_main_flow(
        payload: dict,
        single_repo_processing_flow,  # A function that processes one repository.
        flow_prefix: str,
        batch_size: int,
        num_partitions: int,
        concurrency_limit: int  # This limits the number of concurrent tasks.
):
    logger = get_run_logger()

    # Step 1: Start the flow.
    start_task(flow_prefix)

    # Step 2: Create batches from the payload.
    repos = create_batches_task(payload, batch_size, num_partitions)
    logger.info(f"[{flow_prefix}] Processing {len(repos)} repositories.")

    # Step 3: Retrieve run_id from Prefect context (or use default if not available).
    run_ctx = get_run_context()
    run_id = str(run_ctx.flow_run.id) if run_ctx and run_ctx.flow_run else "default_run_id"

    # Step 4: Create an asyncio queue and enqueue all repository items.
    queue = asyncio.Queue()
    for repo in repos:
        await queue.put(repo)

    # Step 5: Spawn a fixed number of worker tasks to process the queue.
    workers = [asyncio.create_task(worker(queue, run_id, single_repo_processing_flow))
               for _ in range(concurrency_limit)]

    # Wait until all repositories have been processed.
    await queue.join()

    # Cancel all worker tasks, since they're in an infinite loop.
    for w in workers:
        w.cancel()
    await asyncio.gather(*workers, return_exceptions=True)

    # Step 6: Refresh views after processing.
    refresh_views_task(flow_prefix)
    logger.info(f"[{flow_prefix}] Finished flow")



def generic_single_repo_processing_flow(
        repo,
        run_id,
        sub_tasks: list,
        sub_dir: str,
        flow_prefix: str
):

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
