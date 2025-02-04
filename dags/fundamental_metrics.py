import logging
from datetime import datetime
from airflow import DAG
from airflow.decorators import task
from airflow.operators.dummy import DummyOperator
from modular.utils.repository_processor import create_batches, analyze_fundamentals

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

default_args = {
    "owner": "airflow",
    "start_date": datetime(2023, 12, 1),
    "retries": 0,
}

with DAG(
        "fundamental_metrics",
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
        from airflow.operators.python import get_current_context
        context = get_current_context()
        run_id = context["dag_run"].run_id
        logger.info(f"Processing batch with run_id: {run_id} and {len(batch)} repositories")
        analyze_fundamentals(batch, run_id=run_id)

    payload = get_payload()
    batches = get_batches(payload)
    processed = process_batch.expand(batch=batches)
    finalize = DummyOperator(task_id="finalize")
    processed >> finalize
