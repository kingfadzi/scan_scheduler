import yaml
from pathlib import Path
from typing import Dict

class TaskRegistry:
    def __init__(self):
        self.registry = self._load_config()
        self.flat_map = self._flatten_structure()
    
    def _load_config(self) -> Dict:
        config_path = Path(__file__).parent / "task_registry.yaml"
        with open(config_path) as f:
            return yaml.safe_load(f)
    
    def _flatten_structure(self) -> Dict[str, str]:
        flat = {}
        # Core tasks
        for task_name, path in self.registry['core'].items():
            flat[task_name] = path
        
        # Language tasks
        for category in ['languages']:  # Explicitly process languages
            for lang, tasks in self.registry[category].items():
                for task_name, path in tasks.items():
                    flat_key = f"{category}.{lang}.{task_name}"
                    flat[flat_key] = path
        return flat

    
    def validate_task(self, task_key: str) -> bool:
        return task_key in self.flat_map  # Add this method

# Singleton instance
task_registry = TaskRegistry()
