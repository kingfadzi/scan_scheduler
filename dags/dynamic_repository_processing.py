import logging
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from modular.models import Session, Repository, AnalysisExecutionLog, CombinedRepoMetrics
from modular.cloning import CloningAnalyzer
from modular.kantra_analysis import KantraAnalyzer
from modular.utils.query_builder import build_query
from sqlalchemy import text

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
    statuses = session.query(AnalysisExecutionLog.status) \
        .filter(AnalysisExecutionLog.run_id == run_id, AnalysisExecutionLog.repo_id == repo.repo_id) \
        .filter(AnalysisExecutionLog.status != "PROCESSING") \
        .all()
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

def fetch_repositories(payload, batch_size=1000):
    session = Session()
    offset = 0
    base_query = build_query(payload)
    logger.info(f"Built query: {base_query}")
    while True:
        final_query = f"{base_query} OFFSET {offset} LIMIT {batch_size}"
        logger.info(f"Executing query: {final_query}")
        batch = session.query(Repository).from_statement(text(final_query)).all()
        if not batch:
            break
        for repo in batch:
            session.expunge(repo)
        yield batch
        offset += batch_size
    session.close()

def create_batches(payload, batch_size=1000, num_tasks=5):
    all_repos = []
    for batch in fetch_repositories(payload, batch_size):
        all_repos.extend(batch)
    return [all_repos[i::num_tasks] for i in range(num_tasks)]

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 12, 1),
    'retries': 0
}

with DAG(
        'dynamic_repository_processing',
        default_args=default_args,
        schedule_interval=None,
        max_active_tasks=5,
        catchup=False,
) as dag:

    def process_batches(**kwargs):
        dag_run = kwargs.get('dag_run')
        payload = dag_run.conf if dag_run and dag_run.conf else {}
        batches = create_batches(payload, batch_size=1000, num_tasks=5)
        run_id = kwargs.get('run_id') or '{{ run_id }}'
        for i, batch in enumerate(batches):
            logger.info(f"Processing batch {i} with {len(batch)} repositories")
            analyze_repositories(batch, run_id=run_id)

    process_task = PythonOperator(
        task_id="process_batches",
        python_callable=process_batches,
    )

    process_task
