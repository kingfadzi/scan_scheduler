import yaml
from pathlib import Path
from typing import Dict, Any

class TaskRegistry:
    def __init__(self):
        self.registry = self._load_config()
        self.flat_map = self._flatten_structure()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load YAML configuration from package"""
        config_path = Path(__file__).parent / "task_registry.yaml"
        with open(config_path) as f:
            return yaml.safe_load(f)
    
    def _flatten_structure(self) -> Dict[str, str]:
        """Create flat key-path mapping without aliases"""
        flat = {}
        
        # Core tasks
        for task_name, path in self.registry['core'].items():
            flat[task_name] = path
        
        # Language tasks
        for lang, tasks in self.registry['languages'].items():
            for task_name, path in tasks.items():
                flat_key = f"{lang}.{task_name}"
                flat[flat_key] = path
                
        return flat
    
    def validate_task(self, task_key: str) -> bool:
        return task_key in self.flat_map
    
    def get_task_path(self, task_key: str) -> str:
        return self.flat_map[task_key]

# Singleton instance
task_registry = TaskRegistry()
