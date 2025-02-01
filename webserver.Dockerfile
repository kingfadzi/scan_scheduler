FROM airflow-base:latest

ENV AIRFLOW_HOME=/home/airflow/airflow
ENV AIRFLOW_DAGS_FOLDER=${AIRFLOW_HOME}/dags

COPY --chown=airflow:airflow ./dags $AIRFLOW_DAGS_FOLDER
COPY --chown=airflow:airflow ./modular $AIRFLOW_DAGS_FOLDER/modular

COPY --chown=airflow:airflow webserver_entrypoint.sh /usr/local/bin/webserver_entrypoint.sh
RUN chmod +x /usr/local/bin/webserver_entrypoint.sh

USER airflow
WORKDIR $AIRFLOW_HOME
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/webserver_entrypoint.sh"]
