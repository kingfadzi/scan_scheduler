from dataclasses import dataclass
from typing import Callable, Awaitable, Any, List

@dataclass
class ProcessingStrategy:
    process_function: Callable[[Any, dict, str], Awaitable[Any]]
    on_completion_hooks: List[Callable[[Any, Any, Any], None]]