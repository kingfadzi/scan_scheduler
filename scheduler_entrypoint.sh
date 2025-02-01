#!/bin/bash
set -e

if [ -f /tmp/keys/id_ed25519 ]; then
    mkdir -p /home/airflow/.ssh
    cp /tmp/keys/id_ed25519 /home/airflow/.ssh/id_ed25519
    chmod 600 /home/airflow/.ssh/id_ed25519
    chown airflow:airflow /home/airflow/.ssh/id_ed25519
fi

if [ -f /tmp/keys/id_ed25519.pub ]; then
    mkdir -p /home/airflow/.ssh
    cp /tmp/keys/id_ed25519.pub /home/airflow/.ssh/id_ed25519.pub
    chmod 644 /home/airflow/.ssh/id_ed25519.pub
    chown airflow:airflow /home/airflow/.ssh/id_ed25519.pub
fi

if [ -f /tmp/keys/known_hosts ]; then
    mkdir -p /home/airflow/.ssh
    cp /tmp/keys/known_hosts /home/airflow/.ssh/known_hosts
    chmod 644 /home/airflow/.ssh/known_hosts
    chown airflow:airflow /home/airflow/.ssh/known_hosts
fi

if [ -d /home/airflow/.ssh ]; then
    chmod 700 /home/airflow/.ssh
    chown airflow:airflow /home/airflow/.ssh
fi

#rm -rf /home/airflow/.kantra/custom-rulesets
#if ! git clone "$RULESETS_GIT_URL" /home/airflow/.kantra/custom-rulesets; then
#    echo "Git clone failed for repository: $RULESETS_GIT_URL. Exiting..."
 #   exit 1
#fi

rm -f "$AIRFLOW_HOME/airflow-scheduler.pid"

wait_for_service() {
    local host=$1
    local port=$2
    for i in {1..30}; do
        if nc -z "$host" "$port"; then
            return 0
        fi
        sleep 2
    done
    exit 1
}

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

exec airflow scheduler
