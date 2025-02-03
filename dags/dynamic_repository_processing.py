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
        logger.error("❌ No dag_run object found. Cannot extract SQL query.")
        return

    sql_query = dag_run.conf.get('sql')

    if not sql_query:
        logger.info("ℹ️ No SQL query provided.")
    else:
        logger.info(f"✅ Received SQL query: {sql_query}")

# Default DAG arguments
default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 12, 1),
    'retries': 1
}

# Define DAG with the same name
with DAG(
    'dynamic_repository_processing',
    default_args=default_args,
    schedule_interval=None,
    catchup=False,
) as dag:

    log_sql_task = PythonOperator(
        task_id="log_sql_query",
        python_callable=log_sql_query,
        op_kwargs={'dag_run': '{{ dag_run }}'}  # Explicitly pass dag_run
    )

    log_sql_task  # Explicitly link task to DAG