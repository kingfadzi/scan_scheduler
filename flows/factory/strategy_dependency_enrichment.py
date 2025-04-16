from flows.factory.processing_strategy import ProcessingStrategy
from flows.factory.enrichment_dependency_processor import process_dependency_enrichment

dependency_enrichment_strategy = ProcessingStrategy(
    process_function=process_dependency_enrichment,
    on_completion_hooks=[]  # No cleanup or status update needed
)
