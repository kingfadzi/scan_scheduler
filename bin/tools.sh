#!/bin/bash

set -e

# S3 Storage Configuration
S3_URL="http://192.168.1.188:9000"
BUCKET="blobs"
TARBALL="tools.tar.gz"
EXTRACT_DIR="tools"

# Optional authentication
ACCESS_KEY=""
SECRET_KEY=""

# Usage Information
usage() {
    echo "Usage: $0 <command>"
    echo "Commands:"
    echo "  pull  - Download and extract tools.tar.gz"
    echo "  push  - Compress and upload tools.tar.gz"
    exit 1
}

# Ensure correct number of arguments
if [ $# -ne 1 ]; then
    usage
fi

COMMAND="$1"
FINAL_URL="${S3_URL}/${BUCKET}/${TARBALL}"

# Set curl authentication flag if keys are provided
CURL_AUTH=()
if [[ -n "$ACCESS_KEY" && -n "$SECRET_KEY" ]]; then
    CURL_AUTH=(-u "${ACCESS_KEY}:${SECRET_KEY}")
fi

case "$COMMAND" in
    pull)
        echo "Pulling ${TARBALL} from ${FINAL_URL}..."

        # Download with visible progress
        curl --fail --show-error --progress-bar --output "${TARBALL}" "${CURL_AUTH[@]}" "${FINAL_URL}" || {
            echo "Error: Failed to download ${TARBALL}."
            rm -f "${TARBALL}"
            exit 1
        }

        echo "Extracting ${TARBALL}..."
        mkdir -p "${EXTRACT_DIR}"
        tar -xvzf "${TARBALL}" -C "${EXTRACT_DIR}" || { echo "Error: Extraction failed."; exit 1; }
        echo "Extraction complete. Modify contents inside '${EXTRACT_DIR}'."

        # Ensure tools/ is ignored in git
        if ! grep -qxF "${EXTRACT_DIR}/" .gitignore 2>/dev/null; then
            echo "${EXTRACT_DIR}/" >> .gitignore
            echo "Added '${EXTRACT_DIR}/' to .gitignore."
        fi
        ;;

    push)
        # Ensure the directory exists before compressing
        if [ ! -d "${EXTRACT_DIR}" ]; then
            echo "Error: '${EXTRACT_DIR}' does not exist. Nothing to compress."
            exit 1
        fi

        echo "Compressing contents of '${EXTRACT_DIR}' into ${TARBALL}..."
        tar -cvzf "${TARBALL}" -C "${EXTRACT_DIR}" . || { echo "Error: Compression failed."; exit 1; }
        echo "Compression complete."

        echo "Uploading ${TARBALL} to ${FINAL_URL}..."
        curl --fail --show-error --progress-bar -T "${TARBALL}" "${CURL_AUTH[@]}" "${FINAL_URL}" || {
            echo "Error: Upload failed."
            exit 1
        }

        echo "Upload complete. Cleaning up local files..."
        rm -rf "${TARBALL}" "${EXTRACT_DIR}"
        echo "Cleanup complete."
        ;;

    *)
        echo "Invalid command: $COMMAND"
        usage
        ;;
esac