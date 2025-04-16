from flows.factory.processing_strategy import ProcessingStrategy
from flows.factory.repository_processor import process_repository
from flows.factory.cleanup_hook_adapter import cleanup_hook_adapter, status_update_hook_adapter

repository_strategy = ProcessingStrategy(
    process_function=process_repository,
    on_completion_hooks=[
        cleanup_hook_adapter,
        status_update_hook_adapter
    ]
)