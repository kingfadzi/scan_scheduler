from flows.base_tasks import fetch_repositories_task, start_task, clone_repository_task, \
    cleanup_repo_task, update_status_task, refresh_views_task
from prefect import flow, task, get_run_logger, unmapped
from prefect.context import get_run_context
from prefect.task_runners import ConcurrentTaskRunner
from typing import List, Callable, Dict, Any

def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split list into batches of specified size."""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

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
    def repo_subflow(repo: dict, sub_dir: str, sub_tasks: List[Callable], flow_prefix: str, repo_slug: str):
        logger = get_run_logger()
        ctx = get_run_context()
        run_id = str(ctx.flow_run.id) if ctx and hasattr(ctx, 'flow_run') else "default"

        repo_dir = None
        try:
            logger.info(f"Starting processing for {repo_slug}")
            repo_dir = clone_repository_task(repo, run_id, sub_dir)

            for task_fn in sub_tasks:
                try:
                    task_fn(repo_dir, repo, run_id)
                except Exception as e:
                    logger.error(f"Task failed: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Critical failure: {str(e)}")
            raise
        finally:
            if repo_dir:
                try:
                    cleanup_repo_task(repo_dir)
                except Exception as e:
                    logger.warning(f"Cleanup error: {str(e)}")

        try:
            update_status_task(repo, run_id)
        except Exception as e:
            logger.error(f"Status update failed: {str(e)}")

        return repo

    @task(name=f"{default_flow_prefix} - Subflow Trigger",
          task_run_name="{repo[repo_slug]}",
          retries=1)
    def trigger_subflow(repo: dict, sub_dir: str, sub_tasks: List[Callable], flow_prefix: str):
        logger = get_run_logger()
        try:
            return repo_subflow(
                repo,
                sub_dir,
                sub_tasks,
                flow_prefix,
                repo['repo_slug']
            )
        except Exception as e:
            logger.error(f"Subflow failed: {str(e)}")
            return None  # Explicitly return None to continue processing

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
        try:
            start_task(flow_prefix)
            ctx = get_run_context()
            parent_run_id = str(ctx.flow_run.id) if ctx and hasattr(ctx, 'flow_run') else "default"
            logger.info(f"Main flow starting (concurrency: {default_concurrency})")

            repos = fetch_repositories_task(payload, batch_size)
            logger.info(f"Total repositories to process: {len(repos)}")

            repo_batches = chunk_list(repos, batch_size)
            all_results = []

            for batch in repo_batches:
                states = trigger_subflow.map(
                    repo=batch,
                    sub_dir=unmapped(sub_dir),
                    sub_tasks=unmapped(sub_tasks),
                    flow_prefix=unmapped(flow_prefix)
                )

                # Collect successful results
                batch_results = [s.result() for s in states if s.is_completed()]
                all_results.extend([r for r in batch_results if r is not None])

            logger.info(f"Processing complete. Successfully processed {len(all_results)}/{len(repos)} repos")
            return all_results

        except Exception as e:
            logger.error(f"Critical failure: {str(e)}")
            raise
        finally:
            try:
                refresh_views_task(flow_prefix)
            except Exception as e:
                logger.error(f"View refresh failed: {str(e)}")

    return main_flow