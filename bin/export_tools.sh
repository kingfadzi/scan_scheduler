#!/usr/bin/env bash

set -e

# Usage: ./collect_tools.sh <container_id_or_name> <destination_directory>
CONTAINER_ID="$1"
DEST_DIR="$2"

if [ -z "$CONTAINER_ID" ] || [ -z "$DEST_DIR" ]; then
  echo "Usage: $0 <container_id_or_name> <destination_directory>"
  exit 1
fi

mkdir -p "$DEST_DIR"

docker exec "$CONTAINER_ID" tar -czf - \
  -C / \
  usr/local/bin/cloc \
  usr/local/bin/go-entry \
  usr/local/bin/kantra \
  usr/local/bin/grype \
  usr/local/bin/syft \
  usr/local/bin/trivy \
  home/airflow \
> "${DEST_DIR}/tools.tar.gz"

echo "tools.tar.gz has been saved to ${DEST_DIR}/tools.tar.gz"

