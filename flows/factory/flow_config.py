from typing import List
from pydantic import BaseModel, Field, validator
from flows.tasks.registry.task_registry import task_registry

class FlowConfig(BaseModel):
    sub_dir: str = Field(..., min_length=1)
    flow_prefix: str = Field(..., pattern=r'^[a-zA-Z0-9_-]+$')
    additional_tasks: List[str] = Field(default_factory=list)
    processing_batch_workers: int = Field(2, gt=0)
    per_batch_workers: int = Field(5, gt=0)
    task_concurrency: int = Field(3, gt=0)
    parent_run_id: str = Field(..., pattern=r'^[a-zA-Z0-9_-]+$')

    @validator('additional_tasks')
    def validate_tasks(cls, v):
        invalid_tasks = [t for t in v if not task_registry.validate_task(t)]
        if invalid_tasks:
            valid_tasks = "\n- ".join(task_registry.flat_map.keys())
            raise ValueError(
                f"Invalid tasks: {invalid_tasks}\nValid tasks:\n- {valid_tasks}"
            )
        return v