import logging
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def log_payload(**kwargs):
    """
    Extracts and logs the received payload from dag_run.conf.
    """
    dag_run = kwargs.get('dag_run')

    if not dag_run:
        logger.error("Missing dag_run context")
        return

    payload = dag_run.conf  # Extract entire payload

    if not payload:
        logger.info("No payload provided.")
        return

    # Log received payload
    logger.info(f"Received payload: {payload}")

    # Extract and log individual fields (handling missing keys)
    fields = [
        "repo_id",
        "host_name",
        "activity_status",
        "tc",
        "main_language",
        "classification_label",
        "app_id",
        "number_of_contributors"
    ]

    for field in fields:
        values = payload.get(field, [])
        logger.info(f"{field}: {values}")

# Default DAG arguments
default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 12, 1),
    'retries': 0  # Disable retries
}

# Define DAG
with DAG(
        'dynamic_repository_processing',
        default_args=default_args,
        schedule_interval=None,
        catchup=False,
) as dag:

    log_payload_task = PythonOperator(
        task_id="log_payload",
        python_callable=log_payload
    )

    log_payload_task
