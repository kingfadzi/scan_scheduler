import logging
from datetime import datetime
from airflow import DAG
from airflow.decorators import task
from modular.utils.repository_processor import create_batches, analyze_repositories

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 12, 1),
    'retries': 0
}

with DAG(
        'dynamic_repository_processing',
        default_args=default_args,
        schedule_interval=None,
        catchup=False,
) as dag:

    @task
    def get_payload(**kwargs):
        # Retrieve payload from dag_run.conf; if missing, return an empty dict.
        dag_run = kwargs.get('dag_run')
        return dag_run.conf if dag_run and dag_run.conf else {}

    @task
    def get_batches(payload: dict, batch_size: int = 1000, num_tasks: int = 5):
        # Use your decoupled business logic to create batches
        batches = create_batches(payload, batch_size=batch_size, num_tasks=num_tasks)
        logger.info(f"Created {len(batches)} batches.")
        return batches

    @task
    def process_batch(batch, run_id: str):
        # Process one batch using your business logic.
        analyze_repositories(batch, run_id=run_id)

    payload = get_payload()
    batches = get_batches(payload)
    # The run_id can be passed from context or templated; here we use a templated string.
    run_id = "{{ run_id }}"

    # Dynamically map the process_batch task over the list of batches.
    process_batch.expand(batch=batches, run_id=run_id)
