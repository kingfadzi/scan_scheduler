from flows.factory.repository_processor import process_repository
from flows.factory.enrichment_dependency_processor import process_dependency_enrichment
from flows.factory.cleanup_hook_adapter import cleanup_hook_adapter, status_update_hook_adapter
from flows.factory.processing_strategy import ProcessingStrategy

clone_and_process_strategy = ProcessingStrategy(
    process_function=process_repository,
    on_completion_hooks=[cleanup_hook_adapter, status_update_hook_adapter]
)

process_only_strategy = ProcessingStrategy(
    process_function=process_dependency_enrichment,
    on_completion_hooks=[]
)

STRATEGY_REGISTRY = {
    "clone_and_process": clone_and_process_strategy,
    "process_only": process_only_strategy
}

def get_strategy_by_name(name: str):
    return STRATEGY_REGISTRY[name]
