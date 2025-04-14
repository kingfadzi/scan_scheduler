import yaml
from pathlib import Path
from typing import Dict, Any

class TaskRegistry:
    def __init__(self):
        self.registry = self._load_config()
        self.flat_map = self._flatten_structure()

    def _load_config(self) -> Dict[str, Any]:
        config_path = Path(__file__).parent / "task_registry.yaml"
        with open(config_path) as f:
            return yaml.safe_load(f)

    def _flatten_structure(self) -> Dict[str, str]:
        flat = {}

        for task_name, path in self.registry.get('base', {}).items():
            flat[f"base.{task_name}"] = path

        for task_name, path in self.registry.get('core', {}).items():
            flat[f"core.{task_name}"] = path

        for lang, lang_tasks in self.registry.get('languages', {}).items():
            if isinstance(lang_tasks, dict):
                for category, category_tasks in lang_tasks.items():
                    if isinstance(category_tasks, dict):
                         for task_type, path in category_tasks.items():
                            key = f"languages.{lang}.{category}.{task_type}"
                            flat[key] = path
                    else:
                        key = f"languages.{lang}.{category}"
                        flat[key] = category_tasks

        return flat

    def validate_task(self, task_key: str) -> bool:
        return task_key in self.flat_map

    def get_task_path(self, task_key: str) -> str:
        if not self.validate_task(task_key):
            raise KeyError(f"Invalid task key: {task_key}")
        return self.flat_map[task_key]

task_registry = TaskRegistry()
