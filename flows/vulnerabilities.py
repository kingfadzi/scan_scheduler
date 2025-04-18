import asyncio
from config.config import Config
from flows.factory.submitter_flow import submitter_flow

if __name__ == "__main__":
    asyncio.run(submitter_flow(
        payload={
            "analysis_type": "vulnerabilities",
            "host_name": ["github.com"],
            "host_name": [Config.GITLAB_HOSTNAME, Config.BITBUCKET_HOSTNAME],
            "main_language": ["c#", "go", "java", "JavaScript", "Ruby", "Python"]
        },
        processor_deployment="batch_repo_subflow/batch_repo_subflow",
        flow_prefix="VULN",
        batch_size=100,
        check_interval=10,
        sub_dir="vulnerabilities",
        additional_tasks=[
            "core.trivy",
            "core.grype",
            "core.xeol"
        ],
        processing_batch_workers=4,
        per_batch_workers=4,
        task_concurrency=10
    ))
