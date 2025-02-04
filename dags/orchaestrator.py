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

    trigger_fundamental = TriggerDagRunOperator(
        task_id="trigger_fundamental_metrics",
        trigger_dag_id="fundamental_metrics",
        reset_dag_run=True,
        conf="{{ ti.xcom_pull(task_ids='get_payload') | tojson }}",
    )

    def get_external_execution_date(execution_date, **kwargs):
        ti = kwargs["ti"]
        triggered_run_id = ti.xcom_pull(task_ids="trigger_fundamental_metrics")
        from airflow.models import DagRun
        triggered_runs = DagRun.find(dag_id="fundamental_metrics", run_id=triggered_run_id)
        if not triggered_runs:
            raise ValueError(f"No DagRun found for fundamental_metrics with run_id: {triggered_run_id}")
        triggered_run = triggered_runs[0]
        ti.log.info(f"Found external DagRun execution_date: {triggered_run.execution_date}")
        return triggered_run.execution_date

    wait_for_fundamental = ExternalTaskSensor(
        task_id="wait_for_fundamental_finalize",
        external_dag_id="fundamental_metrics",
        external_task_id="finalize",
        allowed_states=["success"],
        failed_states=["failed", "upstream_failed"],
        execution_date_fn=get_external_execution_date,
        check_existence=True,
        mode="poke",  # poke mode so failures are detected immediately
        poke_interval=15,
        timeout=3600,
    )

    trigger_component_patterns = TriggerDagRunOperator(
        task_id="trigger_component_patterns",
        trigger_dag_id="component_patterns",
        reset_dag_run=True,
        conf="{{ ti.xcom_pull(task_ids='get_payload') | tojson }}",
    )

    trigger_standards_assessment = TriggerDagRunOperator(
        task_id="trigger_standards_assessment",
        trigger_dag_id="standards_assessment",
        reset_dag_run=True,
        conf="{{ ti.xcom_pull(task_ids='get_payload') | tojson }}",
    )

    trigger_vulnerability_metrics = TriggerDagRunOperator(
        task_id="trigger_vulnerability_metrics",
        trigger_dag_id="vulnerability_metrics",
        reset_dag_run=True,
        conf="{{ ti.xcom_pull(task_ids='get_payload') | tojson }}",
    )

    payload >> trigger_fundamental
    trigger_fundamental >> wait_for_fundamental
    wait_for_fundamental >> [
        trigger_component_patterns,
        trigger_standards_assessment,
        trigger_vulnerability_metrics,
    ]
