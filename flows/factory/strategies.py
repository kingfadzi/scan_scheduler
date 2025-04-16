from flows.factory.processing_strategy import ProcessingStrategy
from flows.factory.clone_and_process_strategy import clone_and_process_repository
from flows.factory.process_only_strategy import process_only_repository_data
from flows.factory.cleanup_hook_adapter import cleanup_hook_adapter, status_update_hook_adapter

# Strategy: clone → process → cleanup
clone_and_process_strategy = ProcessingStrategy(
    process_function=clone_and_process_repository,
    on_completion_hooks=[cleanup_hook_adapter, status_update_hook_adapter]
)

# Strategy: DB-driven or in-place processing, no cloning/cleanup
process_only_strategy = ProcessingStrategy(
    process_function=process_only_repository_data,
    on_completion_hooks=[]
)

STRATEGY_REGISTRY = {
    "clone_and_process": clone_and_process_strategy,
    "process_only": process_only_strategy
}

def get_strategy_by_name(name: str) -> ProcessingStrategy:
    try:
        return STRATEGY_REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"Unknown strategy type: '{name}'. "
            f"Available strategies: {list(STRATEGY_REGISTRY.keys())}"
        )
