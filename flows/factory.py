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
    # Backwards-compatible parameters
    default_concurrency: Optional[int] = None,  # Deprecated but maintained
    work_pool_name: str = "fundamentals-pool"     # New concurrency control
):
    
    
    # Deprecation warning for default_concurrency
    if default_concurrency is not None:
        import warnings
        warnings.warn(
            "The 'default_concurrency' parameter is deprecated and will be removed in future versions. "
            f"Concurrency is now controlled by the '{work_pool_name}' work pool configuration."
        )

    @flow(name=f"{flow_name} - Subflow", flow_run_name="{repo_slug}")
    async def repo_subflow(
        repo: dict,
        sub_dir: str,
        sub_tasks: List[Callable],
        flow_prefix: str,
        repo_slug: str,
        parent_run_id: str
    ):
        repo_dir = None
        logger = get_run_logger()
        try:
            async with timeout(300):  # 5-minute timeout
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
        batch_size: int = default_batch_size,
        # Dummy parameter for backwards compatibility
        _deprecated_concurrency: Optional[int] = default_concurrency
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
                        parent_task_run_id=ctx.task_run.id,
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

if __name__ == "__main__":
    import asyncio
    from datetime import datetime
    
    async def smoke_test():
        analysis_flow = create_analysis_flow(
            flow_name="Smoke Test Flow",
            flow_run_name=f"smoke-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            default_sub_tasks=[],  # Add your tasks here
            default_sub_dir="/tmp/repos",
            default_flow_prefix="smoke-test",
            # default_concurrency=5  # Still works but shows warning
        )
        
        return await analysis_flow({
            "organization": "test-org",
            "max_repos": 5
        })
    
    try:
        result = asyncio.run(smoke_test())
        print(f" Smoke test result: {result}")
    except Exception as e:
        print(f"Smoke test failed: {str(e)}")