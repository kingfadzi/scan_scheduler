from prefect import flow, task, get_run_logger, unmapped
from prefect.context import get_run_context
from modular.shared.models import Session
from datetime import datetime
from common_tasks import (
    clone_repository_task,
    cleanup_repo_task,
    update_status_task,
    start_task,
    fetch_repositories_task,
    refresh_views_task
)

# Subflow for processing a single repository
@flow(name="Single Repo Processing Flow")
def single_repo_processing_flow(repo, run_id, sub_dir, sub_tasks, flow_prefix):
    logger = get_run_logger()
    with Session() as session:
        attached_repo = session.merge(repo)
        repo_dir = None
        try:
            logger.info(f"[{flow_prefix}] Processing repository: {attached_repo.repo_id}")
            repo_dir = clone_repository_task(attached_repo, run_id, sub_dir)
            for task_fn in sub_tasks:
                # Each task in sub_tasks is expected to accept (repo_dir, attached_repo, session, run_id)
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

# Wrapper task to run the subflow (this enables mapping)
@task(name="Run Single Repo Flow Task")
def run_single_repo_flow_task(repo, run_id, sub_dir, sub_tasks, flow_prefix):
    return single_repo_processing_flow(repo, run_id, sub_dir, sub_tasks, flow_prefix)

# Main flow using native mapping
@flow(name="Main Flow with Mapping")
def main_flow(payload: dict,
              batch_size: int,
              sub_dir: str,
              concurrency_limit: int,
              sub_tasks: list,
              flow_prefix: str):
    logger = get_run_logger()

    # Step 1: Start the flow.
    start_task(flow_prefix)

    # Step 2: Fetch unique repositories.
    repos = fetch_repositories_task(payload, batch_size)
    logger.info(f"[{flow_prefix}] Processing {len(repos)} repositories.")

    # Step 3: Retrieve run_id from Prefect context.
    run_ctx = get_run_context()
    run_id = str(run_ctx.flow_run.id) if run_ctx and run_ctx.flow_run else "default_run_id"

    # Step 4: Map the wrapper task over each repository.
    # NOTE: The max_parallelism parameter is not supported in Prefect's task mapping.
    # To enforce a concurrency limit, configure your task runner accordingly.
    # For example, when running this flow with a DaskTaskRunner, you can set the number of workers:
    #   @flow(task_runner=DaskTaskRunner(cluster_kwargs={"n_workers": concurrency_limit}))
    run_single_repo_flow_task.map(
        repo=repos,
        run_id=unmapped(run_id),
        sub_dir=unmapped(sub_dir),
        sub_tasks=unmapped(sub_tasks),
        flow_prefix=unmapped(flow_prefix)
    )

    # Step 5: Refresh views after processing.
    refresh_views_task(flow_prefix)
    logger.info(f"[{flow_prefix}] Finished flow")
