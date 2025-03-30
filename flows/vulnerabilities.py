from config.config import Config
from tasks.registry import task_registry
import asyncio
from datetime import datetime
from flows.factory6 import create_analysis_flow


VALID_VULN_TASKS = [
    "core.trivy",
    "core.syft",
    "core.grype",
    "core.xeol"
]

vulnerabilities_flow = create_analysis_flow(
    flow_name="vulnerabilities_flow",
    default_sub_dir="vulnerabilities",
    default_flow_prefix="VULN",
    default_additional_tasks=VALID_VULN_TASKS,
    processing_batch_size=Config.DEFAULT_PROCESSING_BATCH_SIZE,
    processing_batch_workers=Config.DEFAULT_PROCESSING_BATCH_WORKERS,
    per_batch_workers=Config.DEFAULT_PER_BATCH_WORKERS,
    task_concurrency=Config.DEFAULT_TASK_CONCURRENCY
)

if __name__ == "__main__":
    asyncio.run(vulnerabilities_flow(
        payload={
            "payload": {
                "host_name": [Config.GITLAB_HOSTNAME]
            }
        }
    ))
