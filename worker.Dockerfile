FROM airflow-base:latest

ARG RULESETS_GIT_URL="git@github.com:kingfadzi/custom-rulesets.git"
ENV RULESETS_GIT_URL=$RULESETS_GIT_URL

ENV AIRFLOW_HOME=/home/airflow/airflow
ENV AIRFLOW_DAGS_FOLDER=${AIRFLOW_HOME}/dags

USER root

# Fix typo in filename and entrypoint reference
COPY --chown=airflow:airflow worker_entrypoint.sh /usr/local/bin/worker_entrypoint.sh
RUN chmod +x /usr/local/bin/worker_entrypoint.sh

RUN mkdir -p $AIRFLOW_DAGS_FOLDER/sql

COPY --chown=airflow:airflow ./dags $AIRFLOW_DAGS_FOLDER
COPY --chown=airflow:airflow ./modular $AIRFLOW_DAGS_FOLDER/modular
COPY --chown=airflow:airflow ./sql $AIRFLOW_DAGS_FOLDER/sql

USER airflow
WORKDIR $AIRFLOW_HOME

ENTRYPOINT ["/usr/local/bin/worker_entrypoint.sh"]