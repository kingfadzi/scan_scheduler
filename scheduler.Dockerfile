FROM airflow-base:1.0

ENV AIRFLOW_HOME=/home/airflow/airflow
ENV AIRFLOW_DAGS_FOLDER=${AIRFLOW_HOME}/dags

COPY --chown=airflow:airflow ./dags $AIRFLOW_DAGS_FOLDER
COPY --chown=airflow:airflow ./modular $AIRFLOW_DAGS_FOLDER/modular

COPY --chown=airflow:airflow scheduler_entrypoint.sh /usr/local/bin/scheduler_entrypoint.sh
RUN chmod +x /usr/local/bin/scheduler_entrypoint.sh

USER airflow
WORKDIR $AIRFLOW_HOME
ENTRYPOINT ["/usr/local/bin/scheduler_entrypoint.sh"]
