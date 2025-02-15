from datetime import timedelta
from prefect import task
from modular.analyzer.cloning import CloningAnalyzer
from modular.shared.utils import determine_final_status
from prefect.cache_policies import NO_CACHE

@task(cache_policy=NO_CACHE)
def clone_repository_task(repo, run_id, sub_dir):
    return CloningAnalyzer().clone_repository(repo=repo, run_id=run_id, sub_dir=sub_dir)

@task(cache_policy=NO_CACHE)
def cleanup_repo_task(repo_dir):
    CloningAnalyzer().cleanup_repository_directory(repo_dir)

@task(cache_policy=NO_CACHE)
def update_status_task(repo, run_id, session):
    determine_final_status(repo, run_id, session)
