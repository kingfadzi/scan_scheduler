import logging
from airflow import DAG
from airflow.operators.python import PythonOperator
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

def analyze_repositories(batch, run_id, **kwargs):
    session = Session()
    for repo in batch:
        try:
            logger.info(f"Processing repository: {repo.repo_name} (ID: {repo.repo_id})")

            repo_dir = CloningAnalyzer().clone_repository(repo=repo, run_id=run_id)
            logger.debug(f"Repository cloned to: {repo_dir}")

            # Uncomment to enable additional analysis tools
            # LizardAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)
            # ClocAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)
            # GoEnryAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)
            # GitLogAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)

            TrivyAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)

            # SyftAndGrypeAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)
            # CheckovAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)
            # SemgrepAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)

        except Exception as e:
            logger.error(f"Error processing repository {repo.repo_name}: {e}")
            repo.status = "ERROR"
            repo.comment = str(e)
            repo.updated_on = datetime.utcnow()
            session.add(repo)
            session.commit()
            logger.info(f"Repository {repo.repo_name} marked as ERROR.")
        finally:
            CloningAnalyzer().cleanup_repository_directory(repo_dir)
            logger.debug(f"Repository directory {repo_dir} cleaned up.")

        determine_final_status(repo, run_id, session)

    session.close()

def determine_final_status(repo, run_id, session):
    """
    Determine the final status of a repository after all analysis runs.
    """
    logger.info(f"Determining final status for repository {repo.repo_name} (ID: {repo.repo_id}) with run_id: {run_id}")

    analysis_statuses = (
        session.query(AnalysisExecutionLog.status)
        .filter(AnalysisExecutionLog.run_id == run_id, AnalysisExecutionLog.repo_id == repo.repo_id)
        .filter(AnalysisExecutionLog.status != "PROCESSING")
        .all()
    )

    if not analysis_statuses:
        repo.status = "ERROR"
        repo.comment = "No analysis records found for this run ID."
    elif any(status == "FAILURE" for (status,) in analysis_statuses):
        repo.status = "FAILURE"
    elif all(status == "SUCCESS" for (status,) in analysis_statuses):
        repo.status = "SUCCESS"
        repo.comment = "All analysis steps completed successfully."
    else:
        repo.status = "UNKNOWN"

    repo.updated_on = datetime.utcnow()
    session.add(repo)
    session.commit()
    logger.info(f"Final status for repository {repo.repo_name}: {repo.status} ({repo.comment})")

def fetch_repositories(batch_size=1000, sql_query=None):
    """
    Fetch repositories dynamically based on the SQL query provided.
    If no query is provided, do nothing.
    """
    if not sql_query:
        logger.info("No SQL query provided. Skipping repository fetching.")
        return []

    session = Session()
    try:
        result = session.execute(text(sql_query)).fetchall()
        repositories = [Repository(**dict(row)) for row in result]

        for i in range(0, len(repositories), batch_size):
            yield repositories[i:i + batch_size]

    except Exception as e:
        logger.error(f"Error executing SQL query: {e}")
        return []

    finally:
        session.close()

def create_batches(batch_size=1000, num_tasks=10, dag_run=None):
    """
    Fetch repositories dynamically based on SQL query from dag_run.conf.
    """
    if not dag_run:
        logger.error("dag_run object is missing. No repositories will be processed.")
        return []

    sql_query = dag_run.conf.get('sql')
    if not sql_query:
        logger.info("No SQL query provided. Skipping repository fetching.")
        return []

    logger.info("Fetching repositories with custom SQL query and creating batches.")
    all_repositories = [repo for batch in fetch_repositories(batch_size, sql_query=sql_query) for repo in batch]

    if not all_repositories:
        logger.info("No repositories found. Skipping batch creation.")
        return []

    task_batches = [all_repositories[i::num_tasks] for i in range(num_tasks)]
    logger.info(f"Created {len(task_batches)} batches for processing.")
    return task_batches

# Default DAG arguments
default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 12, 1),
    'retries': 1
}

# Define the **new** DAG with dynamic SQL support
with DAG(
        'dynamic_repository_processing',
        default_args=default_args,
        schedule_interval=None,
        max_active_tasks=10,
        catchup=False,
) as dag:

    def prepare_batches(**kwargs):
        return create_batches(batch_size=1000, num_tasks=10, dag_run=kwargs['dag_run'])

    batches = prepare_batches(**{'dag_run': '{{ dag_run }}'})

    if batches:
        for task_id, batch in enumerate(batches):
            PythonOperator(
                task_id=f"process_batch_{task_id}",
                python_callable=analyze_repositories,
                op_kwargs={
                    'batch': batch,
                    'run_id': '{{ run_id }}'
                },
            )
    else:
        logger.info("No tasks created because no repositories were fetched.")