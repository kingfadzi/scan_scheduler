import asyncio
from config.config import Config
from flows.factory.submitter_flow import submitter_flow

if __name__ == "__main__":
    asyncio.run(submitter_flow(
        payload={
            "analysis_type": "build_tools",
            "host_name": ["github.com"],
            "activity_status": ["ACTIVE"],
            "main_language": ["Python", "Java", "Go", "JavaScript"]
        },
        processor_deployment="batch_repo_subflow/batch_repo_subflow",
        flow_prefix="BUILD_TOOLS",
        batch_size=100,
        check_interval=10,
        sub_dir="build_tools",
        additional_tasks=[
            "languages.go.build",
            "languages.java.gradle.build",
            "languages.java.maven.build",
            "languages.javascript.build",
            "languages.python.build"
        ],
        processing_batch_workers=4,
        per_batch_workers=4,
        task_concurrency=10
    ))
