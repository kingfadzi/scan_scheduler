from prefect import task, get_run_logger
from prefect.cache_policies import NO_CACHE
from functools import partial
from flows.tasks.base_tasks import cleanup_repo_task, update_status_task

@task(name='Clean Up Repository Task', cache_policy=NO_CACHE)
def cleanup_hook_adapter(flow=None, flow_run=None, state=None):
    logger = get_run_logger()
    try:
        parent_run_id = flow_run.parameters["parent_run_id"]
        repo_dir = None

        if state and isinstance(state, dict):
            repo_dir = state.get("repo_dir")
        elif state and hasattr(state, "result"):
            repo_dir = state.result.get("repo_dir")

        if not repo_dir:
            logger.error("repo_dir was not set in the flow result.")
            return

        return cleanup_repo_task.fn(repo_dir=repo_dir, run_id=parent_run_id)

    except Exception as e:
        logger.exception("Cleanup hook failed unexpectedly")
        raise

@task(name='Update Data Status Task', cache_policy=NO_CACHE)
def status_update_hook_adapter(flow=None, flow_run=None, state=None):
    logger = get_run_logger()
    try:
        repo = flow_run.parameters["repo"]
        parent_run_id = flow_run.parameters["parent_run_id"]
        return update_status_task.fn(repo=repo, run_id=parent_run_id)

    except Exception as e:
        logger.exception("Status update hook failed unexpectedly")
        raise