from datetime import datetime
from airflow import DAG
from airflow.models.param import Param
from airflow.operators.python import PythonOperator

# Define the DAG with a string parameter
default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
}

dag = DAG(
    'log_message_dag',
    default_args=default_args,
    description='A DAG that accepts a string parameter and logs it',
    schedule_interval=None,
    catchup=False,
    params={
        'message': Param('Default message', type='string', description='Message to log')
    }
)

def log_message(**context):
    # Retrieve the message parameter
    message = context['params']['message']

    # Log the message
    context['ti'].log.info(f"Received message: {message}")

with dag:
    log_task = PythonOperator(
        task_id='log_message_task',
        python_callable=log_message,
        provide_context=True
    )
