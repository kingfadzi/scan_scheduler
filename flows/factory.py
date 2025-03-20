from prefect import flow, task, get_run_logger, unmapped
from prefect.context import get_run_context
from prefect.task_runners import ConcurrentTaskRunner
from typing import List, Callable, Dict
from flows.base_tasks import fetch_repositories_task, start_task, clone_repository_task, \
    cleanup_repo_task, update_status_task, refresh_views_task

from prefect import flow, task, get_run_logger, unmapped
from prefect.context import get_run_context
from prefect.task_runners import ConcurrentTaskRunner
from typing import List, Callable, Dict

def create_analysis_flow(
        flow_name: str,
        default_sub_tasks: List[Callable],
        default_sub_dir: str,
        default_flow_prefix: str,
        default_batch_size: int = 10,
        default_concurrency: int = 3
):
    @flow(name=f"{flow_name} - Subflow")
    def repo_subflow(repo: dict, sub_dir: str, sub_tasks: List[Callable], flow_prefix: str):
        logger = get_run_logger()
        ctx = get_run_context()
        run_id = str(ctx.flow_run.id) if ctx and hasattr(ctx, 'flow_run') else "default"

        repo_dir = None
        try:
            repo_dir = clone_repository_task(repo, run_id, sub_dir)
            for task_fn in sub_tasks:
                task_fn(repo, run_id)  # Pass run_id to tasks
        finally:
            if repo_dir:
                cleanup_repo_task(repo_dir)
        update_status_task(repo, run_id)
        return repo

    @task(name=f"{default_flow_prefix} - Subflow Trigger")
    def trigger_subflow(repo: dict, sub_dir: str, sub_tasks: List[Callable], flow_prefix: str):
        """Task that wraps the subflow execution"""
        return repo_subflow(repo, sub_dir, sub_tasks, flow_prefix)

    @flow(name=flow_name, task_runner=ConcurrentTaskRunner(max_workers=default_concurrency))
    def main_flow(
            payload: Dict,
            sub_tasks: List[Callable] = default_sub_tasks,
            sub_dir: str = default_sub_dir,
            flow_prefix: str = default_flow_prefix,
            batch_size: int = default_batch_size
    ):
        logger = get_run_logger()
        start_task(flow_prefix)

        ctx = get_run_context()
        parent_run_id = str(ctx.flow_run.id) if ctx and hasattr(ctx, 'flow_run') else "default"
        logger.info(f"Main flow {parent_run_id} starting")

        repos = fetch_repositories_task(payload, batch_size)

        # Map the task wrapper instead of the flow directly
        results = trigger_subflow.map(
            repo=repos,
            sub_dir=unmapped(sub_dir),
            sub_tasks=unmapped(sub_tasks),
            flow_prefix=unmapped(flow_prefix)
        )

        refresh_views_task(flow_prefix)
        return [r.result() for r in results]

    return main_flow
