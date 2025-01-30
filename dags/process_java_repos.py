# dags/process_java_repos.py
import logging
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from modular.models import Session, Repository, AnalysisExecutionLog, CombinedRepoMetrics
from modular.cloning import CloningAnalyzer
from modular.kantra_analysis import KantraAnalyzer

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def analyze_repositories(batch, run_id, **kwargs):
    session = Session()
    for repo in batch:
        repo_dir = None
        try:
            logger.info(f"Processing: {repo.repo_name} ({repo.repo_id})")
            repo_dir = CloningAnalyzer().clone_repository(repo=repo, run_id=run_id)
            KantraAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)
        except Exception as e:
            logger.error(f"Error for {repo.repo_name}: {e}")
            repo.status = "ERROR"
            repo.comment = str(e)
            repo.updated_on = datetime.utcnow()
            session.add(repo)
            session.commit()
        finally:
            if repo_dir:
                CloningAnalyzer().cleanup_repository_directory(repo_dir)
        determine_final_status(repo, run_id, session)
    session.close()

def determine_final_status(repo, run_id, session):
    logger.info(f"Determining status for {repo.repo_name} ({repo.repo_id}) run_id: {run_id}")
    statuses = (
        session.query(AnalysisExecutionLog.status)
        .filter(AnalysisExecutionLog.run_id == run_id, AnalysisExecutionLog.repo_id == repo.repo_id)
        .filter(AnalysisExecutionLog.status != "PROCESSING")
        .all()
    )
    if not statuses:
        repo.status = "ERROR"
        repo.comment = "No analysis records."
    elif any(s == "FAILURE" for (s,) in statuses):
        repo.status = "FAILURE"
    elif all(s == "SUCCESS" for (s,) in statuses):
        repo.status = "SUCCESS"
        repo.comment = "All steps completed."
    else:
        repo.status = "UNKNOWN"
    repo.updated_on = datetime.utcnow()
    session.add(repo)
    session.commit()

def fetch_repositories(batch_size=1000):
    session = Session()
    offset = 0
    while True:
        batch = (
            session.query(Repository)
            .join(CombinedRepoMetrics, CombinedRepoMetrics.repo_id == Repository.repo_id)
            .filter(CombinedRepoMetrics.main_language == "Java")
            # .filter(CombinedRepoMetrics.activity_status == "ACTIVE")
            # .filter(CombinedRepoMetrics.classification_label != "Code -> Massive")
            .filter(Repository.status == "NEW")
            .offset(offset)
            .limit(batch_size)
            .all()
        )
        if not batch:
            break
        yield batch
        offset += batch_size
    session.close()

def create_batches(batch_size=1000, num_tasks=5):
    all_repos = [r for b in fetch_repositories(batch_size) for r in b]
    return [all_repos[i::num_tasks] for i in range(num_tasks)]

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 12, 1),
    'retries': 1
}

with DAG(
        'process_java_repos',
        default_args=default_args,
        schedule_interval=None,
        max_active_tasks=5,
        catchup=False,
) as dag:
    batches = create_batches(batch_size=1000, num_tasks=5)
    for i, batch in enumerate(batches):
        PythonOperator(
            task_id=f"process_batch_{i}",
            python_callable=analyze_repositories,
            op_kwargs={
                'batch': batch,
                'run_id': '{{ run_id }}'
            },
        )
