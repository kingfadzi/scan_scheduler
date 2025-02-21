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
    batches = list(create_batches(payload, batch_size))
    get_run_logger().info(f"Create Batches Task returning {len(batches)} batches")
    return batches


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
        batch_size: int,
):
    logger = get_run_logger()
    logger.info(f"[{flow_prefix}] Starting generic_main_flow")

    # Step 1: Start the flow.
    start_task(flow_prefix)

    # Step 2: Create batches.
    repo_batches = create_batches_task(payload, batch_size)
    # Because create_batches_task is a Prefect Task, we need to await its result.
    batches = await repo_batches.result() if hasattr(repo_batches, "result") else repo_batches
    logger.info(f"[{flow_prefix}] Retrieved {len(batches)} batches (batch_size={batch_size}).")

    # Step 3: Retrieve run_id from Prefect context.
    run_ctx = get_run_context()
    run_id = str(run_ctx.flow_run.id) if run_ctx and run_ctx.flow_run else "default_run_id"
    logger.info(f"[{flow_prefix}] Using run_id: {run_id}")

    # Step 4: Process each batch sequentially.
    batch_index = 0
    for batch in batches:
        batch_index += 1
        logger.info(f"[{flow_prefix}] Processing batch #{batch_index} with {len(batch)} repos.")
        tasks = []
        for repo in batch:
            repo_slug = getattr(repo, "repo_slug", str(repo))
            logger.debug(f"[{flow_prefix}] Scheduling processing for repo: {repo_slug}")
            task = asyncio.create_task(
                asyncio.to_thread(
                    single_repo_processing_flow,
                    repo,
                    repo_slug,
                    run_id
                )
            )
            tasks.append(task)
        logger.info(f"[{flow_prefix}] Awaiting completion of batch #{batch_index} ({len(tasks)} tasks).")
        await asyncio.gather(*tasks)
        logger.info(f"[{flow_prefix}] Completed processing of batch #{batch_index}.")

    # Step 5: Refresh views after processing all batches.
    logger.info(f"[{flow_prefix}] All batches processed. Refreshing views...")
    refresh_views_task(flow_prefix)
    logger.info(f"[{flow_prefix}] Finished generic_main_flow.")


def generic_single_repo_processing_flow(
        repo,
        run_id,
        sub_tasks: list,
        sub_dir: str,
        flow_prefix: str
):
    logger = get_run_logger()
    repo_slug = getattr(repo, "repo_slug", str(repo))
    logger.info(f"[{flow_prefix}] Entering generic_single_repo_processing_flow for repo: {repo_slug}")
    with Session() as session:
        attached_repo = session.merge(repo)
        repo_dir = None
        try:
            logger.info(f"[{flow_prefix}] Processing repository: {attached_repo.repo_id}")
            repo_dir = clone_repository_task(attached_repo, run_id, sub_dir)
            logger.info(f"[{flow_prefix}] Cloned repository {attached_repo.repo_id} to {repo_dir}")

            for idx, task_fn in enumerate(sub_tasks, start=1):
                logger.info(f"[{flow_prefix}] Running sub-task #{idx} for repository: {attached_repo.repo_id}")
                task_fn(repo_dir, attached_repo, session, run_id)
                logger.info(f"[{flow_prefix}] Completed sub-task #{idx} for repository: {attached_repo.repo_id}")

        except Exception as e:
            logger.error(f"[{flow_prefix}] Error processing repository {attached_repo.repo_id}: {e}")
            attached_repo.status = "ERROR"
            attached_repo.comment = str(e)
            attached_repo.updated_on = datetime.utcnow()
            session.add(attached_repo)
            session.commit()
        finally:
            if repo_dir:
                logger.info(f"[{flow_prefix}] Cleaning up repository directory for: {attached_repo.repo_id}")
                cleanup_repo_task(repo_dir)
        logger.info(f"[{flow_prefix}] Updating processing status for repository: {attached_repo.repo_id}")
        update_status_task(attached_repo, run_id, session)
        logger.info(f"[{flow_prefix}] Exiting generic_single_repo_processing_flow for repository: {attached_repo.repo_id}")
