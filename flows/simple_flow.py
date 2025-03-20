from prefect import flow, task, get_run_logger, unmapped
from prefect.context import get_run_context
from config.config import Config
from flows.base_tasks import fetch_repositories_task, start_task, clone_repository_task, cleanup_repo_task, \
    update_status_task, refresh_views_task
from prefect.task_runners import ConcurrentTaskRunner


@flow(name="Main Flow with Mapping", task_runner=ConcurrentTaskRunner(max_workers=3))
def main_flow(batch_size: int, sub_dir: str, sub_tasks: list, flow_prefix: str, payload: dict, concurrency_limit: int = 3):
    logger = get_run_logger()
    start_task(flow_prefix)

    # Fetch repositories using the provided payload.
    repos = fetch_repositories_task(payload, batch_size)

    # Generate a dummy run id.
    run_ctx = get_run_context()
    run_id = str(run_ctx.flow_run.id) if run_ctx and run_ctx.flow_run else "default_run_id"

    # Map the subflow (wrapped in a task) over the list of repositories.
    mapped_futures = run_repo_subflow_task.map(
        repo=repos,
        run_id=unmapped(run_id),
        sub_dir=unmapped(sub_dir),
        sub_tasks=unmapped(sub_tasks),
        flow_prefix=unmapped(flow_prefix)
    )

    # Explicitly wait for all mapped futures to resolve.
    results = [future.result() for future in mapped_futures]
    logger.info(f"Subflow results: {results}")

    refresh_views_task(flow_prefix)
    logger.info("Finished main flow.")


@task(name="Run Repo Subflow Task")
def run_repo_subflow_task(repo: dict, run_id: str, sub_dir: str, sub_tasks: list, flow_prefix: str):
    return repo_subflow(repo, run_id, sub_dir, sub_tasks, flow_prefix)


@flow(name="Repo Subflow")
def repo_subflow(
        repo: dict,
        run_id: str,
        sub_dir: str,
        sub_tasks: list,
        flow_prefix: str
) -> dict:

    logger = get_run_logger()
    logger.info(f"Starting subflow for repository '{repo['repo_id']}' in flow '{flow_prefix}'")

    repo_dir = None

    try:
        # Clone repository
        logger.info(
            f"Cloning repo '{repo['repo_id']}' (run: {run_id}) "
            f"into directory: {sub_dir}"
        )
        repo_dir = clone_repository_task(repo, run_id, sub_dir)
        logger.info(f"Clone successful: {repo_dir}")

        # Process subtasks
        for sub_task in sub_tasks:
            logger.info(f"Executing '{sub_task.__name__}' on '{repo['repo_id']}'")
            sub_task(repo, run_id)

    except Exception as e:
        logger.error(f"Repository processing failed - {repo['repo_id']}: {e}")

    finally:
        # Cleanup resources
        if repo_dir:
            logger.info(f"Cleaning up directory: {repo_dir}")
            cleanup_repo_task(repo_dir)
        else:
            logger.warning(f"No directory to clean for {repo['repo_id']}")

    # Update final status
    update_status_task(repo, run_id)

    logger.info(f"Completed subflow for {repo['repo_id']}")
    return repo


if __name__ == "__main__":
    # Define the new payload as specified.
    example_payload = {
        "payload": {
            "host_name": [Config.GITLAB_HOSTNAME],
            "activity_status": ["ACTIVE"],
            "main_language": ["Python"]
        }
    }

    main_flow(
        batch_size=10,
        sub_dir="dummy_sub_dir",
        sub_tasks=[],
        flow_prefix="TestFlow",
        payload=example_payload
    )
