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
CURL_AUTH=""
if [[ -n "$ACCESS_KEY" && -n "$SECRET_KEY" ]]; then
    CURL_AUTH="-u ${ACCESS_KEY}:${SECRET_KEY}"
fi

case "$COMMAND" in
    pull)
        echo "Pulling ${TARBALL} from ${FINAL_URL}..."

        # Download with status capture
        HTTP_RESPONSE=$(curl --silent --write-out "%{http_code}" --output "${TARBALL}" ${CURL_AUTH} "${FINAL_URL}")

        # Handle HTTP responses
        case "$HTTP_RESPONSE" in
            200) echo "Download successful." ;;
            404) echo "Error: ${TARBALL} not found." ; rm -f "${TARBALL}" ; exit 1 ;;
            401|403) echo "Error: Authentication failed (HTTP $HTTP_RESPONSE). Check credentials." ; rm -f "${TARBALL}" ; exit 1 ;;
            500) echo "Error: Server error (HTTP 500). Try again later." ; rm -f "${TARBALL}" ; exit 1 ;;
            *) echo "Error: Download failed. HTTP Status: $HTTP_RESPONSE" ; rm -f "${TARBALL}" ; exit 1 ;;
        esac

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
        HTTP_RESPONSE=$(curl --silent --write-out "%{http_code}" --progress-bar -T "${TARBALL}" ${CURL_AUTH} "${FINAL_URL}")

        # Handle HTTP responses
        case "$HTTP_RESPONSE" in
            200|204) echo "Upload complete." ;;
            400) echo "Error: Bad request (HTTP 400). Check settings." ; exit 1 ;;
            401|403) echo "Error: Authentication failed (HTTP $HTTP_RESPONSE). Check credentials." ; exit 1 ;;
            500) echo "Error: Server error (HTTP 500). Try again later." ; exit 1 ;;
            *) echo "Error: Upload failed. HTTP Status: $HTTP_RESPONSE" ; exit 1 ;;
        esac
        ;;

    *)
        echo "Invalid command: $COMMAND"
        usage
        ;;
esac