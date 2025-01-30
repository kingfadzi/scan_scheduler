#!/usr/bin/env bash
set -e

##
# Usage: ./manage.sh <start|stop|restart> <env> <service>
#
# - 'start':   docker compose up -d --build
# - 'stop':    docker compose down
# - 'restart': (stop + start)
#
# <env> is used to find the file ".env-<env>"
# <service> is used to find the file "docker-compose-<service>.yaml"
# Project name is "<env>-<service>"
##

if [ "$#" -ne 3 ]; then
  echo "Usage: $0 <start|stop|restart> <env> <service>"
  exit 1
fi

COMMAND="$1"
ENV_NAME="$2"
SERVICE="$3"

ENV_FILE=".env-$ENV_NAME"
COMPOSE_FILE="docker-compose-$SERVICE.yaml"
PROJECT_NAME="${ENV_NAME}-${SERVICE}"

# Ensure the environment file exists
if [ ! -f "$ENV_FILE" ]; then
  echo "Error: Environment file '$ENV_FILE' not found!"
  exit 1
fi

# Ensure the Compose file exists
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
      up -d --build
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
    echo "Restarting project '$PROJECT_NAME' by stopping then starting..."
    # First, do a stop/down
    docker compose \
      --project-name "$PROJECT_NAME" \
      --env-file "$ENV_FILE" \
      -f "$COMPOSE_FILE" \
      down

    # Then, do a fresh start/up
    docker compose \
      --project-name "$PROJECT_NAME" \
      --env-file "$ENV_FILE" \
      -f "$COMPOSE_FILE" \
      up -d --build
    ;;
  *)
    echo "Invalid command: $COMMAND. Valid commands are 'start', 'stop', or 'restart'."
    exit 1
    ;;
esac
