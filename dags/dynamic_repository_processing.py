from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.hooks.postgres_hook import PostgresHook
from datetime import datetime
import logging

def process_repository_query(**context):
    """Process and log SQL queries from API triggers"""
    # Retrieve SQL from API parameters
    sql = context['dag_run'].conf.get('sql')
    
    if not sql:
        raise ValueError("No SQL query provided in trigger parameters")
    
    # Logging implementation
    logger = logging.getLogger(__name__)
    logger.info("\n\u23E3 RECEIVED QUERY \u23E3\n%s", sql)  # ◄ ASCII separator
    
    # Database execution block
    hook = PostgresHook(postgres_conn_id='postgres_default')
    conn = hook.get_conn()
    
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            
            if cur.description:  # Only fetch results for SELECT queries
                results = cur.fetchall()
                logger.info("Query returned %s rows", len(results))
                logger.debug("Sample results:\n%s", results[:3])
                
            conn.commit()
            
    except Exception as e:
        logger.error("Execution failed: %s", str(e))
        raise
    finally:
        conn.close()

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2025, 2, 2),
    'catchup': False
}

with DAG(
    'dynamic_repository_processing',  # ◄ Your custom DAG ID
    default_args=default_args,
    schedule_interval=None,
    tags=['api', 'repository', 'processing'],
    doc_md=__doc__
) as dag:
    
    process_task = PythonOperator(
        task_id='repository_query_handler',
        python_callable=process_repository_query,
        provide_context=True
    )

process_task
