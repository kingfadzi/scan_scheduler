#!/bin/bash

set -e

# MinIO Configuration
MINIO_URL="http://192.168.1.188:9000"
BUCKET="blobs"
TARBALL="tools.tar.gz"
EXTRACT_DIR="tools"

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
FINAL_URL="${MINIO_URL}/${BUCKET}/${TARBALL}"

case "$COMMAND" in
    pull)
        echo "Pulling ${TARBALL} (${FINAL_URL})..."
        curl --progress-bar -o "${TARBALL}" "${FINAL_URL}" || { echo "Download failed"; exit 1; }

        echo "Extracting ${TARBALL}..."
        mkdir -p "${EXTRACT_DIR}"
        tar -xvzf "${TARBALL}" -C "${EXTRACT_DIR}"
        echo "Extraction complete. Modify contents inside '${EXTRACT_DIR}'."

        # Ensure tools/ is ignored in git
        if ! grep -qxF "${EXTRACT_DIR}/" .gitignore 2>/dev/null; then
            echo "${EXTRACT_DIR}/" >> .gitignore
            echo "Added '${EXTRACT_DIR}/' to .gitignore."
        fi
        ;;

    push)
        echo "Compressing contents of '${EXTRACT_DIR}' into ${TARBALL}..."
        tar -cvzf "${TARBALL}" -C "${EXTRACT_DIR}" .  # Ensures only contents are archived
        echo "Compression complete."

        echo "Uploading ${TARBALL} (${FINAL_URL})..."
        curl --progress-bar -T "${TARBALL}" "${FINAL_URL}"
        echo "Upload complete."
        ;;

    *)
        echo "Invalid command: $COMMAND"
        usage
        ;;
esac