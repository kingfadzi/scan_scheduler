from tasks.base_tasks import (
    fetch_repositories_task,
    start_task,
    clone_repository_task,
    cleanup_repo_task,
    update_status_task,
    refresh_views_task
)
from prefect import flow, get_run_logger
from prefect.context import get_run_context
from prefect.client.orchestration import get_client
from typing import List, Callable, Dict, Optional
from asyncio import timeout
import asyncio

def create_analysis_flow(
    flow_name: str,
    flow_run_name: str,
    default_sub_tasks: List[Callable],
    default_sub_dir: str,
    default_flow_prefix: str,
    default_batch_size: int = 100,
    default_concurrency: Optional[int] = None,  # Silently ignored
    work_pool_name: str = "repo-processing"
):
    @flow(name=f"{flow_name} - Subflow", flow_run_name="{repo_slug}")
    async def repo_subflow(
        repo: dict,
        sub_dir: str,
        sub_tasks: List[Callable],
        flow_prefix: str,
        repo_slug: str,
        parent_run_id: str
    ):
        logger = get_run_logger()
        repo_dir = None
        
        try:
            async with timeout(300):
                logger.info(f"Starting processing for {repo_slug}")
                repo_dir = await clone_repository_task.with_options(retries=1)(repo, sub_dir, parent_run_id)
                
                for task_fn in sub_tasks:
                    try:
                        await task_fn(repo_dir, repo, parent_run_id)
                    except Exception as e:
                        logger.error(f"Task failed: {str(e)}")
                        continue
                        
                return repo
            
        except TimeoutError:
            logger.error(f"Timeout processing {repo_slug}")
            return None
        except Exception as e:
            logger.error(f"Critical failure: {str(e)}")
            raise
        finally:
            await perform_cleanup(repo_dir, repo, repo_slug, parent_run_id, logger)

    async def perform_cleanup(repo_dir, repo, repo_slug, parent_run_id, logger):
        if repo_dir:
            await cleanup_repo_task(repo_dir, parent_run_id)
        await update_status_task(repo, parent_run_id)

    @flow(name=flow_name, flow_run_name=flow_run_name)
    async def main_flow(
        payload: Dict,
        sub_tasks: List[Callable] = default_sub_tasks,
        sub_dir: str = default_sub_dir,
        flow_prefix: str = default_flow_prefix,
        batch_size: int = default_batch_size
    ):
        logger = get_run_logger()
        ctx = get_run_context()
        parent_run_id = str(ctx.flow_run.id)
        
        try:
            await start_task(flow_prefix)
            logger.info(f"Main flow {parent_run_id} starting")
            
            repos = await fetch_repositories_task.with_options(retries=1)(payload, batch_size)
            logger.info(f"Processing {len(repos)} repositories")
            
            async with get_client() as client:
                flow_runs = []
                for repo in repos:
                    flow_run = await client.create_flow_run(
                        flow_name=f"{flow_name} - Subflow",
                        parameters={
                            "repo": repo,
                            "sub_dir": sub_dir,
                            "sub_tasks": sub_tasks,
                            "flow_prefix": flow_prefix,
                            "repo_slug": repo['repo_slug'],
                            "parent_run_id": parent_run_id
                        },
                        tags=[flow_prefix, "subflow"],
                        
                        work_pool_name=work_pool_name
                    )
                    flow_runs.append(flow_run.id)
                
                total = len(flow_runs)
                last_completed = 0
                while True:
                    completed = 0
                    for run_id in flow_runs:
                        state = (await client.read_flow_run(run_id)).state
                        if state and state.is_completed():
                            completed += 1
                    
                    if completed > last_completed:
                        logger.info(f"Progress: {completed}/{total} ({completed/total:.1%})")
                        last_completed = completed
                    
                    if completed >= total:
                        break
                        
                    await asyncio.sleep(30)

                return f"Processed {completed}/{total} repositories"
            
        except Exception as e:
            logger.error(f"Critical failure: {str(e)}")
            raise
        finally:
            await refresh_views_task(flow_prefix)

    return main_flow