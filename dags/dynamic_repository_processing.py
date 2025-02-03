import logging
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def build_query(payload):
    base_query = """
        SELECT bitbucket_repositories.*
        FROM bitbucket_repositories
        JOIN combined_repo_metrics 
          ON combined_repo_metrics.repo_id = bitbucket_repositories.repo_id
        WHERE 1=1
    """

    # Map payload keys to their respective columns.
    # Note: repo_id comes from bitbucket_repositories; all other fields come from combined_repo_metrics.
    filter_mapping = {
        'repo_id': 'bitbucket_repositories.repo_id',
        'host_name': 'combined_repo_metrics.host_name',
        'activity_status': 'combined_repo_metrics.activity_status',
        'tc': 'combined_repo_metrics.tc',
        'main_language': 'combined_repo_metrics.main_language',
        'classification_label': 'combined_repo_metrics.classification_label',
        'app_id': 'combined_repo_metrics.app_id',
        'number_of_contributors': 'combined_repo_metrics.number_of_contributors'
    }

    filters = []
    for key, column in filter_mapping.items():
        if key in payload:
            value = payload[key]
            # If the value is a list, generate an IN clause.
            if isinstance(value, list):
                if value:  # Only add filter if the list is not empty.
                    # For lists of strings, generate case-insensitive comparisons.
                    if all(isinstance(v, str) for v in value):
                        formatted_values = ", ".join(f"LOWER('{v.lower()}')" for v in value)
                        filters.append(f"LOWER({column}) IN ({formatted_values})")
                    else:
                        formatted_values = ", ".join(str(v) for v in value)
                        filters.append(f"{column} IN ({formatted_values})")
            else:
                # For single values, use case-insensitive equality for strings.
                if isinstance(value, str):
                    filters.append(f"LOWER({column}) = LOWER('{value}')")
                else:
                    filters.append(f"{column} = {value}")

    if filters:
        base_query += " AND " + " AND ".join(filters)

    return base_query

def log_query(**kwargs):
    dag_run = kwargs.get('dag_run')
    if not dag_run:
        logger.error("Missing dag_run context")
        return

    payload = dag_run.conf
    if not payload:
        logger.info("No payload provided; constructing query with no filters.")
        payload = {}

    query = build_query(payload)
    logger.info(f"Constructed Query: {query}")

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

    log_query_task = PythonOperator(
        task_id="log_query",
        python_callable=log_query
    )

    log_query_task
