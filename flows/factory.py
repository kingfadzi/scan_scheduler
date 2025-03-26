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
from typing import List, Callable, Dict, Optional
import asyncio
from anyio import move_on_after

def create_analysis_flow(
    flow_name: str,
    flow_run_name: str,
    default_sub_tasks: List[Callable],
    default_sub_dir: str,
    default_flow_prefix: str,
    default_batch_size: int = 10,
    default_concurrency: int = 10
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
            async with move_on_after(300):
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
            try:
                await cleanup_repo_task(repo_dir, parent_run_id)
                logger.info(f"Cleanup completed for {repo_slug}")
            except Exception as e:
                logger.warning(f"Cleanup error: {str(e)}")
        
        try:
            await update_status_task(repo, parent_run_id)
            logger.info(f"Status update completed for {repo_slug}")
        except Exception as e:
            logger.error(f"Status update failed: {str(e)}")

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
        progress_task = None  # Initialize progress task
        
        try:
            # Fixed: Ensure start_task is async-compatible
            await start_task(flow_prefix)
            
            logger.info(f"Main flow starting with concurrency {default_concurrency}")
            repos = await fetch_repositories_task.with_options(retries=1)(payload, batch_size)
            
            sem = asyncio.Semaphore(default_concurrency)
            total = len(repos)
            processed = 0
            
            async def process_repo(repo):
                nonlocal processed
                async with sem:
                    result = await repo_subflow(
                        repo=repo,
                        sub_dir=sub_dir,
                        sub_tasks=sub_tasks,
                        flow_prefix=flow_prefix,
                        repo_slug=repo['repo_slug'],
                        parent_run_id=parent_run_id
                    )
                    processed += 1
                    return result
            
            tasks = [process_repo(repo) for repo in repos]
            
            async def report_progress():
                while processed < total:
                    logger.info(f"Progress: {processed}/{total}")
                    await asyncio.sleep(5)
            
            progress_task = asyncio.create_task(report_progress())
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            successful = [r for r in results if not isinstance(r, (Exception, type(None)))]
            logger.info(f"Completed: {len(successful)}/{len(repos)}")
            return successful
            
        except Exception as e:
            logger.error(f"Critical failure: {str(e)}")
            raise
        finally:
            try:
                if progress_task:  # Add null check before cancellation
                    progress_task.cancel()
                # Fixed: Ensure refresh_views_task is async-compatible
                await refresh_views_task(flow_prefix)
                logger.info("View refresh completed")
            except Exception as e:
                logger.error(f"View refresh failed: {str(e)}")

    return main_flow