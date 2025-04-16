# flows/factory/strategies.py
from flows.factory.strategy_repository import repository_strategy
from flows.factory.strategy_dependency_enrichment import dependency_enrichment_strategy

STRATEGY_REGISTRY = {
    "repository": repository_strategy,
    "dependency_enrichment": dependency_enrichment_strategy,
}

def get_strategy_by_name(name: str):
    return STRATEGY_REGISTRY[name]