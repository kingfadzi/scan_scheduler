import logging
from datetime import datetime
from airflow import DAG
from airflow.decorators import task, get_current_context
from modular.utils.repository_processor import create_batches, analyze_repositories

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 12, 1),
    'retries': 0,
}

with DAG(
        'dynamic_repository_processing',
        default_args=default_args,
        schedule_interval=None,
        catchup=False,
) as dag:

    @task
    def get_payload(**kwargs):
        dag_run = kwargs.get("dag_run")
        return dag_run.conf if dag_run and dag_run.conf else {}

    @task
    def get_batches(payload: dict, batch_size: int = 1000, num_tasks: int = 5):
        batches = create_batches(payload, batch_size=batch_size, num_tasks=num_tasks)
        logger.info(f"Created {len(batches)} batches.")
        return batches

    @task
    def process_batch(batch):
        # Retrieve the run_id from the task context at runtime.
        context = get_current_context()
        run_id = context["dag_run"].run_id
        logger.info(f"Processing batch with run_id: {run_id} and {len(batch)} repositories")
        analyze_repositories(batch, run_id=run_id)

    payload = get_payload()
    batches = get_batches(payload)
    # Dynamically map process_batch over the list of batches.
    process_batch.expand(batch=batches)
