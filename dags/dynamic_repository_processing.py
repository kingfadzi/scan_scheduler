import logging
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup
from datetime import datetime
from modular.cloning import CloningAnalyzer
from modular.gitlog_analysis import GitLogAnalyzer
from modular.go_enry_analysis import GoEnryAnalyzer
from modular.lizard_analysis import LizardAnalyzer
from modular.cloc_analysis import ClocAnalyzer
from modular.syft_grype_analysis import SyftAndGrypeAnalyzer
from modular.trivy_analysis import TrivyAnalyzer
from modular.checkov_analysis import CheckovAnalyzer
from modular.semgrep_analysis import SemgrepAnalyzer
from modular.models import Session, Repository, AnalysisExecutionLog, RepoMetrics
from sqlalchemy import text

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def analyze_repositories(batch, run_id):
    session = Session()
    for repo in batch:
        try:
            logger.info(f"Processing repository: {repo.repo_name} (ID: {repo.repo_id})")
            repo_dir = CloningAnalyzer().clone_repository(repo=repo, run_id=run_id)
            logger.debug(f"Repository cloned to: {repo_dir}")

            TrivyAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)

        except Exception as e:
            logger.error(f"Error processing repository {repo.repo_name}: {e}")
            repo.status = "ERROR"
            repo.comment = str(e)
            repo.updated_on = datetime.utcnow()
            session.add(repo)
            session.commit()
        finally:
            CloningAnalyzer().cleanup_repository_directory(repo_dir)

    session.close()

def fetch_repositories(batch_size=1000, sql_query=None):
    if not sql_query:
        logger.info("No SQL query provided. Skipping repository fetching.")
        return []

    session = Session()
    try:
        result = session.execute(text(sql_query)).fetchall()
        repositories = [Repository(**dict(row)) for row in result]
        return [repositories[i:i + batch_size] for i in range(0, len(repositories), batch_size)]

    except Exception as e:
        logger.error(f"Error executing SQL query: {e}")
        return []

    finally:
        session.close()

def create_batches(ti, batch_size=1000, num_tasks=10, **kwargs):
    """
    Fetch repositories dynamically based on the SQL query provided in dag_run.conf.
    """
    dag_run = kwargs.get('dag_run')
    if not dag_run:
        logger.error("dag_run object is missing. No repositories will be processed.")
        return []

    sql_query = dag_run.conf.get('sql')
    if not sql_query:
        logger.info("No SQL query provided. Skipping repository fetching.")
        return []

    logger.info("Fetching repositories with custom SQL query and creating batches.")
    task_batches = fetch_repositories(batch_size, sql_query)

    if not task_batches:
        logger.info("No repositories found. Skipping batch creation.")
        return []

    ti.xcom_push(key='batches', value=task_batches)

# Default DAG arguments
default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 12, 1),
    'retries': 1
}

with DAG(
        'dynamic_repository_processing',
        default_args=default_args,
        schedule_interval=None,
        max_active_tasks=10,
        catchup=False,
) as dag:

    prepare_batches_task = PythonOperator(
        task_id="prepare_batches",
        python_callable=create_batches,
        op_kwargs={'batch_size': 1000, 'num_tasks': 10},
        provide_context=True
    )

    with TaskGroup(group_id="process_batches_group") as process_batches_group:
        def process_batch(task_id, **kwargs):
            ti = kwargs['ti']
            batches = ti.xcom_pull(task_ids="prepare_batches", key="batches")
            
            if not batches or task_id >= len(batches):
                logger.info(f"Skipping process_batch_{task_id} as there is no data.")
                return
            
            batch = batches[task_id]
            run_id = kwargs.get('run_id', 'manual_run')
            analyze_repositories(batch, run_id)

        batch_processing_tasks = [
            PythonOperator(
                task_id=f"process_batch_{i}",
                python_callable=process_batch,
                provide_context=True,
                op_kwargs={'task_id': i}
            )
            for i in range(10)
        ]

    prepare_batches_task >> process_batches_group