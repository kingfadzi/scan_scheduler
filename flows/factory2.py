import asyncio
from prefect import flow, get_run_logger, get_client
from prefect.context import get_run_context
from pydantic import BaseModel, Field, validator
from typing import Dict, List

from tasks.base_tasks import (
    fetch_repositories_task,
    start_task,
    clone_repository_task,
    cleanup_repo_task,
    update_status_task,
    refresh_views_task
)

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
    additional_tasks: List[str] = Field(default_factory=list)

    @validator('additional_tasks')
    def validate_tasks(cls, value):
        invalid = set(value) - TASK_REGISTRY.keys()
        if invalid:
            raise ValueError(f'Invalid tasks: {invalid}')
        return value

@flow(name="repo_subflow", persist_result=True, retries=0)
async def repo_subflow(config: FlowConfig, repo: Dict):
    logger = get_run_logger()
    ctx = get_run_context()
    repo_slug = repo.get("repo_slug", "unknown")

    repo_dir = None
    try:
        repo_dir = await clone_repository_task(repo, config.sub_dir, ctx.flow_run.id)

        for task_name in config.additional_tasks:
            module_path, fn_name = TASK_REGISTRY[task_name].rsplit('.', 1)
            module = __import__(module_path, fromlist=[fn_name])
            await getattr(module, fn_name)(repo_dir, repo, ctx.flow_run.id)

        return {"status": "success", "repo": repo_slug}

    except Exception as e:
        logger.error(f"Subflow failed for {repo_slug}: {e}")
        return {"status": "failed", "repo": repo_slug, "error": str(e)}

    finally:
        await asyncio.gather(
            cleanup_repo_task(repo_dir, ctx.flow_run.id),
            update_status_task(repo, ctx.flow_run.id),
            return_exceptions=True
        )

async def submit_subflow(config: FlowConfig, repo: Dict) -> str:
    async with get_client() as client:
        deployment = await client.read_deployment_by_name("repo_subflow/repo_subflow-deployment")
        flow_run = await client.create_flow_run_from_deployment(
            deployment.id,
            parameters={"config": config.model_dump(), "repo": repo}
        )
        return flow_run.id

def create_analysis_flow(
        flow_name: str,
        default_sub_dir: str,
        default_flow_prefix: str,
        default_additional_tasks: List[str] = None,
        default_batch_size: int = 100
):
    @flow(name=flow_name, description="Continuous repository processing", validate_parameters=False)
    async def main_flow(payload: Dict, sub_dir: str = default_sub_dir,
                        flow_prefix: str = default_flow_prefix,
                        additional_tasks: List[str] = default_additional_tasks or []):
        logger = get_run_logger()
        config = FlowConfig(sub_dir=sub_dir, flow_prefix=flow_prefix, additional_tasks=additional_tasks)

        try:
            await start_task(flow_prefix)
            futures = []
            repo_count = 0

            async for repo in fetch_repositories_task(payload, default_batch_size):
                repo_count += 1
                futures.append(asyncio.create_task(submit_subflow(config, repo)))

                if len(futures) % 5 == 0:
                    await asyncio.sleep(0)

            if futures:
                results = await asyncio.gather(*futures, return_exceptions=True)
                success = sum(1 for r in results if not isinstance(r, Exception))
                logger.info(f"Completed {success}/{len(results)} subflows")

            return f"Processed {repo_count} repositories"

        finally:
            await refresh_views_task(flow_prefix)
            logger.info("Cleanup completed")

    return main_flow
