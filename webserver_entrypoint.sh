#!/bin/bash

set -e

echo "DEBUG: POSTGRES_HOST=${POSTGRES_HOST}"
echo "DEBUG: POSTGRES_PORT=${POSTGRES_PORT}"
echo "DEBUG: AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=${AIRFLOW__DATABASE__SQL_ALCHEMY_CONN}"

wait_for_service() {
    local host=$1
    local port=$2
    for i in {1..30}; do
        if nc -z "$host" "$port"; then
            return 0
        fi
        sleep 2
    done
    echo "Error: $host:$port is not reachable after 30 retries."
    exit 1
}

rm -f "$AIRFLOW_HOME/airflow-webserver.pid"
wait_for_service "$POSTGRES_HOST" "$POSTGRES_PORT"
airflow db init

if ! airflow users list | grep -q "$AIRFLOW_ADMIN_USERNAME"; then
    airflow users create \
        --username "$AIRFLOW_ADMIN_USERNAME" \
        --firstname "$AIRFLOW_ADMIN_FIRSTNAME" \
        --lastname "$AIRFLOW_ADMIN_LASTNAME" \
        --role Admin \
        --email "$AIRFLOW_ADMIN_EMAIL" \
        --password "$AIRFLOW_ADMIN_PASSWORD"
fi

exec airflow webserver --port "${AIRFLOW_HOST_PORT:-8080}"
