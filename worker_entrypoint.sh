#!/bin/bash
set -e

# --- SSH and Keys Setup ---
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

if [ -f /tmp/keys/java.cacerts ]; then
    cp /tmp/keys/java.cacerts /home/airflow/java.cacerts
    chmod 755 /home/airflow/java.cacerts
    chown airflow:airflow /home/airflow/java.cacerts
fi

if [ -d /home/airflow/.ssh ]; then
    chmod 700 /home/airflow/.ssh
    chown airflow:airflow /home/airflow/.ssh
fi

# --- Clone Custom Rulesets ---
rm -rf /home/airflow/.kantra/custom-rulesets
if ! git clone "$RULESETS_GIT_URL" /home/airflow/.kantra/custom-rulesets; then
    echo "Git clone failed for repository: $RULESETS_GIT_URL. Exiting..."
    exit 1
fi

# --- Worker-specific: Get the Queue Name ---
if [ -z "$1" ]; then
    echo "Usage: $0 <worker_queue>"
    exit 1
fi

WORKER_QUEUE="$1"
echo "Starting Celery worker on queue: $WORKER_QUEUE"

# --- Execute the Worker ---
exec celery worker --queues "$WORKER_QUEUE"



