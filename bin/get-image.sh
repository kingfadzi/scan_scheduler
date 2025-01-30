#!/bin/bash

BASE_URL="docker://registry.example.com/repo/"  # Replace with your actual registry URL

if [ -z "$1" ]; then
  echo "Usage: ./get-image.sh <image:tag>"
  exit 1
fi

IMAGE_TAG="$1"
SOURCE="${BASE_URL}${IMAGE_TAG}"
DESTINATION="docker-daemon:${IMAGE_TAG}"

echo "Copying ${IMAGE_TAG} from registry into Docker..."
docker run --rm \
  -v "$HOME/.docker:/root/.docker:ro" \
  -v "/var/run/docker.sock:/var/run/docker.sock" \
  skopeo:latest copy --src-tls-verify=false "${SOURCE}" "${DESTINATION}"

if [ $? -ne 0 ]; then
  echo "Error: skopeo copy failed."
  exit 1
fi

echo "Successfully loaded ${IMAGE_TAG} into Docker."

exit 0
