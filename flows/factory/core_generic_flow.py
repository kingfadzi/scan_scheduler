from prefect import flow, get_run_logger
from prefect.context import get_run_context
from flows.factory.flow_config import FlowConfig
from flows.factory.processing_strategy import ProcessingStrategy

@flow(
    name="process_single_repo_flow",
    persist_result=False,
    retries=0,
    flow_run_name=lambda: get_run_context().parameters["repo"]["repo_id"]
)
async def process_single_repo_flow(
    config: FlowConfig,
    repo: dict,
    parent_run_id: str,
    strategy: ProcessingStrategy
):
    logger = get_run_logger()
    repo_id = repo.get("repo_id", "unknown")
    logger.info(f"[{repo_id}] Starting processing flow.")
    return await strategy.process_function(config, repo, parent_run_id)