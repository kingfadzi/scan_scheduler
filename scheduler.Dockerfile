FROM airflow-base:1.0

ENV AIRFLOW_HOME=/home/airflow/airflow
ENV AIRFLOW_DAGS_FOLDER=${AIRFLOW_HOME}/dags

ARG KANTRA_RULESETS_GIT_URL="https://github.com/kingfadzi/custom-rulesets.git"

COPY --chown=airflow:airflow ./dags $AIRFLOW_DAGS_FOLDER
COPY --chown=airflow:airflow ./modular $AIRFLOW_DAGS_FOLDER/modular

RUN mkdir -p /home/airflow/.kantra && \
    git clone "${KANTRA_RULESETS_GIT_URL}" /home/airflow/.kantra/custom-rulesets && \
    chown -R airflow:airflow /home/airflow/.kantra

COPY --chown=airflow:airflow scheduler_entrypoint.sh /usr/local/bin/scheduler_entrypoint.sh
RUN chmod +x /usr/local/bin/scheduler_entrypoint.sh

USER airflow
WORKDIR $AIRFLOW_HOME
ENTRYPOINT ["/usr/local/bin/scheduler_entrypoint.sh"]
