import logging
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def log_sql_query(**kwargs):
    """
    Extracts and logs the SQL query from the API request (dag_run.conf).
    """
    dag_run = kwargs.get('dag_run')

    if not dag_run:
        logger.error("Missing dag_run context")
        return

    sql_query = dag_run.conf.get('sql')
    if sql_query:
        logger.info(f"Received SQL query: {sql_query}")
    else:
        logger.info("No SQL query provided.")

# Default DAG arguments
default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 12, 1),
    'retries': 0  # Disable retries for all tasks
}

# Define DAG
with DAG(
    'dynamic_repository_processing',
    default_args=default_args,
    schedule_interval=None,
    catchup=False,
) as dag:

    log_sql_task = PythonOperator(
        task_id="log_sql_query",
        python_callable=log_sql_query,
        retries=0  # Explicitly disable retries for this task
    )

    log_sql_task