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
        dag_run = kwargs.get('dag_run')
        return dag_run.conf if dag_run and dag_run.conf else {}

    @task
    def get_run_id(**kwargs):
        # Extract run_id from the context if available; otherwise use a default.
        # This task returns a concrete value that can be used downstream.
        return kwargs.get('run_id', "default_run_id")

    @task
    def get_batches(payload: dict, batch_size: int = 1000, num_tasks: int = 5):
        batches = create_batches(payload, batch_size=batch_size, num_tasks=num_tasks)
        logger.info(f"Created {len(batches)} batches.")
        return batches

    @task
    def process_batch(batch, run_id: str):
        analyze_repositories(batch, run_id=run_id)

    payload = get_payload()
    run_id = get_run_id()  # This returns a concrete value, not a templated variable.
    batches = get_batches(payload)

    # Using partial to set the constant run_id and then expand over batches.
    process_batch.partial(run_id=run_id).expand(batch=batches)
