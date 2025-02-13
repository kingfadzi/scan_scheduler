#!/usr/bin/env bash
set -e

##
# Usage:
#
# For airflow:
#   ./manage_component.sh <start|stop|restart> <env> airflow
#
# For worker:
#   ./manage_component.sh <start|stop|restart> <env> worker <component>
#
# Examples:
#   ./manage_component.sh start production airflow
#   ./manage_component.sh start production worker fundamental_metrics
#
# - 'start':   Builds (without cache) and then starts the containers in detached mode.
# - 'stop':    Stops and removes the containers.
# - 'restart': Stops, rebuilds (without cache), and starts the containers.
#
# <env> is used to locate the file ".env-<env>"
# For airflow, the Compose file is "docker-compose-airflow.yaml"
# For worker,  the Compose file is "docker-compose-worker.yaml"
# The project name will be:
#   - For airflow: "<env>-airflow"
#   - For worker:  "<env>-worker-<component>"
#
# For workers, this script sets the WORKER_QUEUE environment variable for docker-compose.
##

if [ "$#" -lt 3 ]; then
  echo "Usage:"
  echo "  For airflow: $0 <start|stop|restart> <env> airflow"
  echo "  For worker:  $0 <start|stop|restart> <env> worker <component>"
  exit 1
fi

COMMAND="$1"
ENV_NAME="$2"
SERVICE_TYPE="$3"

if [ "$SERVICE_TYPE" = "worker" ]; then
  if [ "$#" -ne 4 ]; then
    echo "Usage for worker: $0 <start|stop|restart> <env> worker <component>"
    exit 1
  fi
  COMPONENT="$4"
  COMPOSE_FILE="docker-compose-worker.yaml"
  PROJECT_NAME="${ENV_NAME}-worker-${COMPONENT}"
  # Export WORKER_QUEUE so that docker-compose substitutes it in the file
  export WORKER_QUEUE="${COMPONENT}"
elif [ "$SERVICE_TYPE" = "airflow" ]; then
  if [ "$#" -ne 3 ]; then
    echo "Usage for airflow: $0 <start|stop|restart> <env> airflow"
    exit 1
  fi
  COMPOSE_FILE="docker-compose-airflow.yaml"
  PROJECT_NAME="${ENV_NAME}-airflow"
else
  echo "Invalid service type: $SERVICE_TYPE. Valid options are 'airflow' or 'worker'."
  exit 1
fi

ENV_FILE=".env-${ENV_NAME}"

# Check for the required environment file
if [ ! -f "$ENV_FILE" ]; then
  echo "Error: Environment file '$ENV_FILE' not found!"
  exit 1
fi

# Check for the required Docker Compose file
if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Error: Docker Compose file '$COMPOSE_FILE' not found!"
  exit 1
fi

case "$COMMAND" in
  start)
    echo "Starting project '$PROJECT_NAME' using '$ENV_FILE' and '$COMPOSE_FILE'..."
    docker compose \
      --project-name "$PROJECT_NAME" \
      --env-file "$ENV_FILE" \
      -f "$COMPOSE_FILE" \
      build --no-cache
    docker compose \
      --project-name "$PROJECT_NAME" \
      --env-file "$ENV_FILE" \
      -f "$COMPOSE_FILE" \
      up -d
    ;;
  stop)
    echo "Stopping project '$PROJECT_NAME' using '$ENV_FILE' and '$COMPOSE_FILE'..."
    docker compose \
      --project-name "$PROJECT_NAME" \
      --env-file "$ENV_FILE" \
      -f "$COMPOSE_FILE" \
      down
    ;;
  restart)
    echo "Restarting project '$PROJECT_NAME' by stopping, rebuilding, then starting..."
    docker compose \
      --project-name "$PROJECT_NAME" \
      --env-file "$ENV_FILE" \
      -f "$COMPOSE_FILE" \
      down
    docker compose \
      --project-name "$PROJECT_NAME" \
      --env-file "$ENV_FILE" \
      -f "$COMPOSE_FILE" \
      build --no-cache
    docker compose \
      --project-name "$PROJECT_NAME" \
      --env-file "$ENV_FILE" \
      -f "$COMPOSE_FILE" \
      up -d
    ;;
  *)
    echo "Invalid command: $COMMAND. Valid commands are 'start', 'stop', or 'restart'."
    exit 1
    ;;
esac