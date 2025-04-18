import asyncio
from config.config import Config
from flows.factory.submitter_flow import submitter_flow

if __name__ == "__main__":
    asyncio.run(submitter_flow(
        payload={
            "analysis_type": "standards",
            "host_name": ["github.com"],
            "activity_status": ["ACTIVE"]
            # "main_language": ["Python"]
        },
        processor_deployment="batch_repo_subflow/batch_repo_subflow-deployment",
        flow_prefix="STAN",
        batch_size=100,
        check_interval=10,
        sub_dir="standards_assessment",
        additional_tasks=["core.iac_components", "core.semgrep"],
        processing_batch_workers=4,
        per_batch_workers=4,
        task_concurrency=10
    ))