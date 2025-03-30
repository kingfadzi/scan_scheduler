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
        for category, items in self.registry.items():
            if isinstance(items, dict):
                for key, value in items.items():
                    if isinstance(value, dict):
                        for sub_key, path in value.items():
                            flat[f"{key}.{sub_key}"] = path
                    else:
                        flat[key] = value
        return flat
    
    def validate_task(self, task_key: str) -> bool:
        return task_key in self.flat_map  # Add this method

# Singleton instance
task_registry = TaskRegistry()
