import logging
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
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
        max_active_tasks=5,
        catchup=False,
) as dag:

    def process_batches(**kwargs):
        dag_run = kwargs.get('dag_run')
        payload = dag_run.conf if dag_run and dag_run.conf else {}
        batches = create_batches(payload, batch_size=5, num_tasks=5)
        run_id = kwargs.get('run_id') or '{{ run_id }}'
        for i, batch in enumerate(batches):
            logger.info(f"Processing batch {i} with {len(batch)} repositories")
            analyze_repositories(batch, run_id=run_id)

    process_task = PythonOperator(
        task_id="process_batches",
        python_callable=process_batches,
    )

    process_task
