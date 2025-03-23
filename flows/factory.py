from tasks.base_tasks import fetch_repositories_task, start_task, clone_repository_task, \
    cleanup_repo_task, update_status_task, refresh_views_task
from prefect import flow, task, get_run_logger, unmapped
from prefect.context import get_run_context
from prefect.task_runners import ConcurrentTaskRunner
from prefect.states import State
from typing import List, Callable, Dict


def create_analysis_flow(
        flow_name: str,
        flow_run_name: str,
        default_sub_tasks: List[Callable],
        default_sub_dir: str,
        default_flow_prefix: str,
        default_batch_size: int = 10,
        default_concurrency: int = 3
):

    @flow(name=f"{flow_name} - Subflow", flow_run_name="{repo_slug}")
    def repo_subflow(
            repo: dict,
            sub_dir: str,
            sub_tasks: List[Callable],
            flow_prefix: str,
            repo_slug: str,
            parent_run_id: str
    ):
        logger = get_run_logger()
        run_id = parent_run_id
        repo_dir = None

        try:
            logger.info(f"Starting processing for {repo_slug} under parent run {parent_run_id}")
            repo_dir = clone_repository_task.with_options(retries=1)(repo, sub_dir, run_id)

            for task_fn in sub_tasks:
                try:
                    task_fn(repo_dir, repo, run_id)
                except Exception as e:
                    logger.error(f"Task {task_fn.__name__} failed: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Critical failure: {str(e)}")
            raise
        finally:
            if repo_dir:
                try:
                    cleanup_repo_task(repo_dir, run_id)
                    logger.info(f"Cleanup completed for {repo_slug}")
                except Exception as e:
                    logger.warning(f"Cleanup error: {str(e)}")

            try:
                update_status_task(repo, repo_dir, run_id)
                logger.info(f"Status: {repo['status']} update completed for {repo_slug}")
            except Exception as e:
                logger.error(f"Status update failed: {str(e)}")

        return repo

    @task(name=f"{default_flow_prefix} - Subflow Trigger",
          task_run_name="{repo[repo_slug]}",
          retries=1)
    def trigger_subflow(
            repo: dict,
            sub_dir: str,
            sub_tasks: List[Callable],
            flow_prefix: str,
            parent_run_id: str
    ):
        logger = get_run_logger()
        try:
            return repo_subflow(
                repo,
                sub_dir,
                sub_tasks,
                flow_prefix,
                repo['repo_slug'],
                parent_run_id
            )
        except Exception as e:
            logger.error(f"Subflow failed: {str(e)}")
            return None

    @flow(name=flow_name,
          flow_run_name=flow_run_name,
          task_runner=ConcurrentTaskRunner(max_workers=default_concurrency))
    def main_flow(
            payload: Dict,
            sub_tasks: List[Callable] = default_sub_tasks,
            sub_dir: str = default_sub_dir,
            flow_prefix: str = default_flow_prefix,
            batch_size: int = default_batch_size
    ):
        logger = get_run_logger()
        all_results = []

        try:
            start_task(flow_prefix)
            ctx = get_run_context()
            parent_run_id = str(ctx.flow_run.id)  # Parent run ID
            logger.info(f"Main flow {parent_run_id} starting with concurrency {default_concurrency}")

            repos = fetch_repositories_task.with_options(retries=1)(payload, batch_size)
            logger.info(f"Total repositories to process: {len(repos)}")

            states: List[State] = trigger_subflow.map(
                repo=repos,
                sub_dir=unmapped(sub_dir),
                sub_tasks=unmapped(sub_tasks),
                flow_prefix=unmapped(flow_prefix),
                parent_run_id=unmapped(parent_run_id),
                return_state=True
            )

            successful = []
            for state in states:
                if state.is_completed():
                    try:
                        result = state.result()
                        if result is not None:
                            successful.append(result)
                    except Exception as e:
                        logger.error(f"Failed to retrieve result: {str(e)}")
                else:
                    error_msg = state.message[:200] if state.message else "Unknown error"
                    logger.warning(f"Failed processing: {error_msg}")

            logger.info(f"Processing complete. Total successful: {len(successful)}/{len(repos)}")
            return successful

        except Exception as e:
            logger.error(f"Critical flow failure: {str(e)}")
            raise
        finally:
            try:
                refresh_views_task(flow_prefix)
                logger.info("View refresh completed")
            except Exception as e:
                logger.error(f"View refresh failed: {str(e)}")

    return main_flow
