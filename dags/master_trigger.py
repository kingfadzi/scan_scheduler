from datetime import datetime
from airflow import DAG
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

default_args = {
    "owner": "airflow",
    "start_date": datetime(2023, 12, 1),
}

with DAG(
        "master_trigger",
        default_args=default_args,
        schedule_interval=None,  # Externally triggered
        catchup=False,
) as dag:

    trigger_fundamental_metrics = TriggerDagRunOperator(
        task_id="trigger_fundamental_metrics",
        trigger_dag_id="fundamental_metrics",  # Triggers the fundamental_metrics DAG
        reset_dag_run=True,
        conf="{{ dag_run.conf | tojson }}",
    )

    trigger_component_patterns = TriggerDagRunOperator(
        task_id="trigger_component_patterns",
        trigger_dag_id="component_patterns",  # Triggers the component_patterns DAG
        reset_dag_run=True,
        conf="{{ dag_run.conf | tojson }}",
    )

    trigger_standards_assessment = TriggerDagRunOperator(
        task_id="trigger_standards_assessment",
        trigger_dag_id="standards_assessment",  # Triggers the standards_assessment DAG
        reset_dag_run=True,
        conf="{{ dag_run.conf | tojson }}",
    )

    trigger_vulnerability_metrics = TriggerDagRunOperator(
        task_id="trigger_vulnerability_metrics",
        trigger_dag_id="vulnerability_metrics",  # Triggers the vulnerability_metrics DAG
        reset_dag_run=True,
        conf="{{ dag_run.conf | tojson }}",
    )

    # Example: you can trigger all in parallel or set dependencies.
    # Here we trigger fundamental_metrics first, then all others in parallel.
    trigger_fundamental_metrics >> [trigger_component_patterns,
                                    trigger_standards_assessment,
                                    trigger_vulnerability_metrics]
