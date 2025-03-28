import asyncio
import json
import time

from prefect import flow, get_run_logger
from prefect.context import get_run_context
from pydantic import BaseModel, Field
from typing import List, Dict
from prefect.client import get_client

from tasks.base_tasks import (
    fetch_repositories_task,
    start_task,
    clone_repository_task,
    cleanup_repo_task,
    update_status_task,
    refresh_views_task
)

# Task registry mapping task keys to module paths
TASK_REGISTRY = {
    "clone": "tasks.base_tasks.clone_repository_task",
    "cleanup": "tasks.base_tasks.cleanup_repo_task",
    "update_status": "tasks.base_tasks.update_status_task",
    "go": "tasks.go_tasks.run_go_build_tool_task",
    "js": "tasks.javascript_tasks.run_javascript_build_tool_task",
    "gradle": "tasks.java_tasks.run_gradlejdk_task",
    "maven": "tasks.java_tasks.run_mavenjdk_task",
    "python": "tasks.python_tasks.run_python_build_tool_task"
}

class FlowConfig(BaseModel):
    sub_dir: str = Field(..., min_length=1)
    flow_prefix: str = Field(..., pattern=r'^[a-zA-Z0-9_-]+$')
    additional_tasks: List[str] = Field(
        default=[],
        description=f"Available tasks: {list(TASK_REGISTRY.keys())}"
    )

    def validate_tasks(self):
        valid_tasks = set(TASK_REGISTRY.keys())
        invalid_tasks = set(self.additional_tasks) - valid_tasks
        if invalid_tasks:
            raise ValueError(f"Invalid tasks: {invalid_tasks}")

# --- Dynamic Subflow ---
# This flow must be deployed separately (with the deployment name "repo_subflow-deployment")
@flow(
    name="repo_subflow",
    persist_result=True,
    retries=0  # Disable retries to prevent AwaitingRetry states
)
async def repo_subflow(config: FlowConfig, repo: Dict):
    logger = get_run_logger()
    parent_run_id = str(get_run_context().flow_run.id)

    repo_dir = None
    result = {"status": "failed", "repo": repo.get("repo_slug", "unknown")}
    try:
        logger.info(f"[Subflow] Starting for repo: {repo.get('repo_slug', 'unknown')}")
        repo_dir = await clone_repository_task(repo, config.sub_dir, parent_run_id)
        for task_name in config.additional_tasks:
            module_path, fn_name = TASK_REGISTRY[task_name].rsplit('.', 1)
            module = __import__(module_path, fromlist=[fn_name])
            task_fn = getattr(module, fn_name)
            await task_fn(repo_dir, repo, parent_run_id)
        result["status"] = "success"
        logger.info(f"[Subflow] Finished successfully for repo: {repo.get('repo_slug', 'unknown')}")
        return result
    except Exception as e:
        logger.error(f"[Subflow] Failed for repo {repo.get('repo_slug', 'unknown')}: {e}")
        result["error"] = str(e)
        return result
    finally:
        await asyncio.gather(
            cleanup_repo_task(repo_dir, parent_run_id),
            update_status_task(repo, parent_run_id),
            return_exceptions=True
        )

# --- Utility Function to Submit the Dynamic Subflow ---
async def submit_subflow(config: FlowConfig, repo: Dict) -> str:
    logger = get_run_logger()
    repo_slug = repo.get("repo_slug", "unknown")

    try:
        logger.info(f"[Submit] Starting submission for {repo_slug}")

        # Load your deployment to obtain the underlying Flow object.
        async with get_client() as client:
            # Get deployment by name
            deployment = await client.read_deployment_by_name("repo_subflow/repo_subflow-deployment")

            # Create flow run directly using deployment ID
            flow_run = await client.create_flow_run_from_deployment(
                deployment.id,
                parameters={
                    "config": config.dict(),
                    "repo": json.loads(json.dumps(repo, default=str))
                }
            )
        return flow_run.id

    except Exception as e:
        logger.error(f"[Submit] Failed: {str(e)}", exc_info=True)
        raise

# --- Main Flow Factory ---
def create_analysis_flow(
    flow_name: str,
    default_sub_dir: str,
    default_flow_prefix: str,
    default_additional_tasks: List[str] = None,
    default_batch_size: int = 100
):
    @flow(
        name=flow_name,
        description="Main flow for continuous repository processing",
        validate_parameters=False
    )
    async def main_flow(
            payload: Dict,
            sub_dir: str = default_sub_dir,
            flow_prefix: str = default_flow_prefix,
            additional_tasks: List[str] = default_additional_tasks or []
    ):
        logger = get_run_logger()
        logger.info(f"[Main] Initializing {flow_name} with prefix: {flow_prefix}")

        try:
            # Initialize configuration with validation
            config = FlowConfig(
                sub_dir=sub_dir,
                flow_prefix=flow_prefix,
                additional_tasks=additional_tasks
            )
            config.validate_tasks()

            # Start tracking
            await start_task(flow_prefix)
            futures = []
            repo_count = 0
            batch_counter = 0

            logger.info("[Main] Starting repository fetch...")
            async for repo in fetch_repositories_task(payload, default_batch_size):
                repo_count += 1
                batch_counter += 1
                repo_slug = repo.get("repo_slug", "unknown")

                try:
                    logger.debug(f"[Main] Processing repo #{repo_count}: {repo_slug}")

                    # Submit subflow
                    task = asyncio.create_task(submit_subflow(config, repo))
                    futures.append(task)
                    logger.debug(f"[Main] Submitted subflow for {repo_slug} (Total: {len(futures)})")

                    # Yield control every 5 submissions to prevent event loop starvation
                    if batch_counter % 5 == 0:
                        logger.debug("[Main] Yielding event loop control")
                        await asyncio.sleep(0)
                        batch_counter = 0

                except Exception as e:
                    logger.error(f"[Main] Critical error processing {repo_slug}: {str(e)}", exc_info=True)
                    continue

            logger.info(f"[Main] Completed repository iteration. Total fetched: {repo_count}")

            # Process submitted tasks
            if futures:
                logger.info(f"[Main] Awaiting completion of {len(futures)} subflows...")
                start_time = time.perf_counter()

                try:
                    results = await asyncio.gather(*futures, return_exceptions=True)
                    duration = time.perf_counter() - start_time

                    success_count = 0
                    for idx, result in enumerate(results, 1):
                        if isinstance(result, Exception):
                            logger.error(f"[Main] Subflow #{idx} failed: {str(result)}")
                        else:
                            logger.debug(f"[Main] Subflow #{idx} succeeded: {result}")
                            success_count += 1

                    logger.info(
                        f"[Main] Subflow completion summary - "
                        f"Success: {success_count}/{len(results)} "
                        f"({duration:.2f}s)"
                    )

                except asyncio.CancelledError:
                    logger.warning("[Main] Subflow gathering cancelled")
                    raise
                except Exception as e:
                    logger.critical(f"[Main] Catastrophic failure in subflow processing: {str(e)}", exc_info=True)
                    raise

            else:
                logger.warning("[Main] No subflows were submitted")

            return f"Processed {repo_count} repositories"

        except StopAsyncIteration:
            logger.info("[Main] Repository iteration completed normally")
        except GeneratorExit:
            logger.warning("[Main] Generator exited prematurely")
            raise
        except Exception as e:
            logger.critical(f"[Main] Flow failed: {str(e)}", exc_info=True)
            raise
        finally:
            logger.info("[Main] Starting final cleanup")
            await refresh_views_task(flow_prefix)
            logger.info("[Main] Cleanup completed")

    return main_flow
