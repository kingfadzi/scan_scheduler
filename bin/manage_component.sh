#!/usr/bin/env bash
set -e

##
# Usage:
# For airflow: ./manage_component.sh <start|stop|restart> <env> airflow
# For worker:  ./manage_component.sh <start|stop|restart> <env> worker <component>
##

# --- Validation ---
if [ "$#" -lt 3 ]; then
  echo "ERROR: Invalid arguments"
  echo "Usage for airflow: $0 <start|stop|restart> <env> airflow"
  echo "Usage for worker:  $0 <start|stop|restart> <env> worker <component>"
  exit 1
fi

COMMAND="$1"
ENV_NAME="$2"
SERVICE_TYPE="$3"

# --- Worker Configuration ---
if [ "$SERVICE_TYPE" = "worker" ]; then
  if [ "$#" -ne 4 ]; then
    echo "ERROR: Missing component name for worker"
    echo "Usage: $0 <start|stop|restart> <env> worker <component>"
    exit 1
  fi
  COMPONENT="$4"
  
  # Validate component name format
  if [[ ! "$COMPONENT" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "ERROR: Invalid component name '$COMPONENT'"
    echo "Must contain only letters, numbers, dashes and underscores"
    exit 1
  fi

  export WORKER_QUEUE="$COMPONENT"
  COMPOSE_FILE="docker-compose-worker.yaml"
  PROJECT_NAME="${ENV_NAME}-worker-${COMPONENT}"

# --- Airflow Configuration ---
elif [ "$SERVICE_TYPE" = "airflow" ]; then
  if [ "$#" -ne 3 ]; then
    echo "ERROR: Invalid arguments for airflow"
    echo "Usage: $0 <start|stop|restart> <env> airflow"
    exit 1
  fi
  COMPOSE_FILE="docker-compose-airflow.yaml"
  PROJECT_NAME="${ENV_NAME}-airflow"

else
  echo "ERROR: Invalid service type '$SERVICE_TYPE'"
  echo "Valid options: 'airflow' or 'worker'"
  exit 1
fi

# --- Environment Setup ---
ENV_FILE=".env-${ENV_NAME}"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: Environment file '$ENV_FILE' not found!"
  exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "ERROR: Docker compose file '$COMPOSE_FILE' not found!"
  exit 1
fi

# --- Command Handling ---
case "$COMMAND" in
  start)
    echo "Starting $SERVICE_TYPE service '$PROJECT_NAME'..."
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
    echo "Stopping $SERVICE_TYPE service '$PROJECT_NAME'..."
    docker compose \
      --project-name "$PROJECT_NAME" \
      --env-file "$ENV_FILE" \
      -f "$COMPOSE_FILE" \
      down
    ;;

  restart)
    echo "Restarting $SERVICE_TYPE service '$PROJECT_NAME'..."
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
    echo "ERROR: Invalid command '$COMMAND'"
    echo "Valid commands: start, stop, restart"
    exit 1
    ;;
esac

echo "Operation completed successfully for $SERVICE_TYPE service '$PROJECT_NAME'"
