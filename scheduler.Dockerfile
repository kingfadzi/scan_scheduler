FROM airflow-base:1.0

COPY --chown=airflow:airflow ./dags $AIRFLOW_DAGS_FOLDER
COPY --chown=airflow:airflow ./modular $AIRFLOW_DAGS_FOLDER/modular

USER airflow
WORKDIR /home/airflow/airflow
