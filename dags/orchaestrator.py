import logging
from datetime import datetime
from airflow import DAG
from airflow.decorators import task
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sensors.external_task import ExternalTaskSensor

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

default_args = {
    "owner": "airflow",
    "start_date": datetime(2023, 12, 1),
    "retries": 0,
}

with DAG(
        "orchestrator_dag",
        default_args=default_args,
        schedule_interval=None,
        catchup=False,
) as dag:

    @task
    def get_payload(**kwargs):
        dag_run = kwargs.get("dag_run")
        payload = dag_run.conf if dag_run and dag_run.conf else {}
        logger.info(f"Received payload: {payload}")
        return payload

    payload = get_payload()

    trigger_fundamentals = TriggerDagRunOperator(
        task_id="trigger_fundamentals_metrics",
        trigger_dag_id="fundamentals_metrics",
        reset_dag_run=True,
        conf="{{ ti.xcom_pull(task_ids='get_payload') }}",
    )

    wait_for_fundamentals = ExternalTaskSensor(
        task_id="wait_for_fundamentals_metrics",
        external_dag_id="fundamentals_metrics",
        external_task_id=None,
        allowed_states=["success"],
        timeout=600,
        poke_interval=30,
        mode="reschedule",
    )

    trigger_component_patterns = TriggerDagRunOperator(
        task_id="trigger_component_patterns",
        trigger_dag_id="component_patterns",
        reset_dag_run=True,
        conf="{{ ti.xcom_pull(task_ids='get_payload') }}",
    )

    trigger_standards_assessment = TriggerDagRunOperator(
        task_id="trigger_standards_assessment",
        trigger_dag_id="standards_assessment",
        reset_dag_run=True,
        conf="{{ ti.xcom_pull(task_ids='get_payload') }}",
    )

    trigger_vulnerability_metrics = TriggerDagRunOperator(
        task_id="trigger_vulnerability_metrics",
        trigger_dag_id="vulnerability_metrics",
        reset_dag_run=True,
        conf="{{ ti.xcom_pull(task_ids='get_payload') }}",
    )

    payload >> trigger_fundamentals
    trigger_fundamentals >> wait_for_fundamentals
    wait_for_fundamentals >> [trigger_component_patterns, trigger_standards_assessment, trigger_vulnerability_metrics]
