#!/usr/bin/env bash
set -e

##
# Usage: ./manage.sh <start|stop|restart> <env> <service>
#
# - 'start':   docker compose build --no-cache && docker compose up -d
# - 'stop':    docker compose down
# - 'restart': (stop + build + start)
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

    # 1. Build (no cache)
    docker compose \
      --project-name "$PROJECT_NAME" \
      --env-file "$ENV_FILE" \
      -f "$COMPOSE_FILE" \
      build --no-cache

    # 2. Bring up containers
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
    echo "Restarting project '$PROJECT_NAME' by stopping, building, then starting..."

    # 1. Stop/down
    docker compose \
      --project-name "$PROJECT_NAME" \
      --env-file "$ENV_FILE" \
      -f "$COMPOSE_FILE" \
      down

    # 2. Build (no cache)
    docker compose \
      --project-name "$PROJECT_NAME" \
      --env-file "$ENV_FILE" \
      -f "$COMPOSE_FILE" \
      build --no-cache

    # 3. Start containers
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
