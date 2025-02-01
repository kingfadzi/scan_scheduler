FROM airflow-base:latest

ARG RULESETS_GIT_URL="git@github.com:kingfadzi/custom-rulesets.git"
ENV RULESETS_GIT_URL=$RULESETS_GIT_URL

ENV AIRFLOW_HOME=/home/airflow/airflow
ENV AIRFLOW_DAGS_FOLDER=${AIRFLOW_HOME}/dags

USER root

COPY --chown=airflow:airflow ./dags $AIRFLOW_DAGS_FOLDER
COPY --chown=airflow:airflow ./modular $AIRFLOW_DAGS_FOLDER/modular

RUN chmod -R airflow:airflow $AIRFLOW_DAGS_FOLDER
RUN chmod -R airflow:airflow AIRFLOW_DAGS_FOLDER/modular

COPY --chown=airflow:airflow scheduler_entrypoint.sh /usr/local/bin/scheduler_entrypoint.sh
RUN chmod +x /usr/local/bin/scheduler_entrypoint.sh

USER airflow
WORKDIR $AIRFLOW_HOME

ENTRYPOINT ["/usr/local/bin/scheduler_entrypoint.sh"]
