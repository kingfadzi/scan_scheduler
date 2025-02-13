#!/bin/bash
set -e

# --- SSH and Keys Setup ---
[ -f /tmp/keys/id_ed25519 ] && {
    mkdir -p /home/airflow/.ssh
    cp /tmp/keys/id_ed25519 /home/airflow/.ssh/
    chmod 600 /home/airflow/.ssh/id_ed25519
    chown airflow:airflow /home/airflow/.ssh/id_ed25519
}

[ -f /tmp/keys/id_ed25519.pub ] && {
    cp /tmp/keys/id_ed25519.pub /home/airflow/.ssh/
    chmod 644 /home/airflow/.ssh/id_ed25519.pub
    chown airflow:airflow /home/airflow/.ssh/id_ed25519.pub
}

[ -f /tmp/keys/known_hosts ] && {
    cp /tmp/keys/known_hosts /home/airflow/.ssh/
    chmod 644 /home/airflow/.ssh/known_hosts
    chown airflow:airflow /home/airflow/.ssh/known_hosts
}

[ -f /tmp/keys/java.cacerts ] && {
    cp /tmp/keys/java.cacerts /home/airflow/
    chmod 755 /home/airflow/java.cacerts
    chown airflow:airflow /home/airflow/java.cacerts
}

[ -d /home/airflow/.ssh ] && {
    chmod 700 /home/airflow/.ssh
    chown airflow:airflow /home/airflow/.ssh
}

# --- Clone Custom Rulesets ---
if ! git clone "$RULESETS_GIT_URL" /home/airflow/.kantra/custom-rulesets; then
    echo "ERROR: Failed cloning rulesets from $RULESETS_GIT_URL"
    exit 1
fi

# --- Queue Validation ---
if [ -z "$WORKER_QUEUE" ] && [ $# -eq 0 ]; then
    echo "CRITICAL: Missing queue name. Use either:"
    echo "1. Pass as first argument to container"
    echo "2. Set WORKER_QUEUE environment variable"
    exit 1
fi

QUEUE_NAME="${1:-$WORKER_QUEUE}"
echo "Starting Celery worker for queue: $QUEUE_NAME"

# --- Start Worker ---
exec airflow celery worker \
    --queues "$QUEUE_NAME" \
    --pid "/tmp/worker-${QUEUE_NAME}.pid"
