from flows.base_tasks import fetch_repositories_task, start_task, clone_repository_task, \
    cleanup_repo_task, update_status_task, refresh_views_task
from prefect import flow, task, get_run_logger, unmapped
from prefect.context import get_run_context
from prefect.task_runners import ConcurrentTaskRunner
from typing import List, Callable, Dict, Optional
from prefect.futures import PrefectFuture
from prefect.states import State

def create_analysis_flow(
        flow_name: str,
        flow_run_name: str,
        default_sub_tasks: List[Callable],
        default_sub_dir: str,
        default_flow_prefix: str,
        default_batch_size: int = 10,
        default_concurrency: int = 3
):

    @flow(name=f"{flow_name} - Subflow", 
          flow_run_name="{repo_slug}",
          # Allow subflow to fail without crashing parent flow
          allow_failure=True)  
    def repo_subflow(repo: dict, sub_dir: str, sub_tasks: List[Callable], flow_prefix: str, repo_slug: str):
        logger = get_run_logger()
        ctx = get_run_context()
        run_id = str(ctx.flow_run.id) if ctx and hasattr(ctx, 'flow_run') else "default"

        repo_dir = None
        try:
            logger.info(f"Starting processing for {repo_slug}")
            repo_dir = clone_repository_task.with_options(retries=2, retry_delay_seconds=10)(repo, run_id, sub_dir)
            
            for task_fn in sub_tasks:
                try:
                    # Allow individual tasks to fail
                    task_fn.with_options(allow_failure=True)(repo_dir, repo, run_id)
                except Exception as e:
                    logger.error(f"Task {task_fn.__name__} failed for {repo_slug}: {str(e)}")
                    continue  # Continue to next task
                    
        except Exception as e:
            logger.error(f"Critical failure in subflow {repo_slug}: {str(e)}")
            raise  # Re-raise to mark subflow as failed
        finally:
            try:
                if repo_dir:
                    cleanup_repo_task(repo_dir)
            except Exception as e:
                logger.warning(f"Cleanup failed for {repo_slug}: {str(e)}")

        try:
            update_status_task.with_options(allow_failure=True)(repo, run_id)
        except Exception as e:
            logger.error(f"Status update failed for {repo_slug}: {str(e)}")

        return repo

    @task(name=f"{default_flow_prefix} - Subflow Trigger", 
          task_run_name="{repo[repo_slug]}",
          # Allow task to fail without stopping parent flow
          allow_failure=True,
          retries=2)
    def trigger_subflow(repo: dict, sub_dir: str, sub_tasks: List[Callable], flow_prefix: str):
        """Task that wraps the subflow execution"""
        try:
            return repo_subflow(repo, sub_dir, sub_tasks, flow_prefix, repo['repo_slug'])
        except Exception as e:
            get_run_logger().error(f"Subflow failed for {repo['repo_slug']}: {str(e)}")
            raise  # Will be caught by task's allow_failure=True

    @flow(name=flow_name, 
          flow_run_name=flow_run_name, 
          task_runner=ConcurrentTaskRunner(max_workers=default_concurrency),
          # Continue on failure to process all repos
          return_state=True)
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
            logger.info(f"Main flow {parent_run_id} starting with concurrency {default_concurrency}")

            repos = fetch_repositories_task.with_options(
                retries=3, 
                retry_delay_seconds=30
            )(payload, batch_size)

            logger.info(f"Processing {len(repos)} repositories")

            # Process results with state handling
            states: List[State] = trigger_subflow.map(
                repo=repos,
                sub_dir=unmapped(sub_dir),
                sub_tasks=unmapped(sub_tasks),
                flow_prefix=unmapped(flow_prefix)
            )

            # Handle successful results
            successful = [s.result() for s in states if s.is_completed()]
            logger.info(f"Successfully processed {len(successful)}/{len(repos)} repos")

            # Handle failures
            failures = [s for s in states if s.is_failed()]
            if failures:
                logger.warning(f"{len(failures)} repositories failed processing")
                for state in failures:
                    try:
                        logger.error(f"Failure reason: {state.message}")
                    except Exception:
                        pass

            return successful

        except Exception as e:
            logger.error(f"Critical flow failure: {str(e)}")
            raise
        finally:
            try:
                refresh_views_task.with_options(
                    allow_failure=True,
                    retries=2
                )(flow_prefix)
            except Exception as e:
                logger.error(f"Failed to refresh views: {str(e)}")

    return main_flow