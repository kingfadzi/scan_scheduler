from prefect import flow
from prefect.task_runners import ConcurrentTaskRunner

PER_BATCH_WORKERS = 10

@flow(task_runner=ConcurrentTaskRunner(max_workers=PER_BATCH_WORKERS))
async def batch_build_profiles_flow(repo_ids: list[str], batch_number: int):
    for repo_id in repo_ids:
        build_profile_flow(repo_id=repo_id, batch_number=batch_number)