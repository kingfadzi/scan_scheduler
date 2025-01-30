#!/usr/bin/env bash

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <destination-directory>"
  exit 1
fi

DEST=$1
echo "Destination: $DEST"

# cloc
if [ ! -f /usr/local/bin/cloc ]; then
  echo "Error: /usr/local/bin/cloc not found."
  exit 1
fi
mkdir -p "${DEST}/tools/cloc"
echo "Copying cloc..."
cp /usr/local/bin/cloc "${DEST}/tools/cloc/"

# kantra + .kantra config
if [ ! -f /usr/local/bin/kantra ]; then
  echo "Error: /usr/local/bin/kantra not found."
  exit 1
fi
mkdir -p "${DEST}/tools/kantra"
echo "Copying kantra..."
cp /usr/local/bin/kantra "${DEST}/tools/kantra/"
if [ ! -d /root/tools/.kantra ]; then
  echo "Error: /root/tools/.kantra directory not found."
  exit 1
fi
echo "Copying .kantra config..."
cp -r /root/tools/.kantra/* "${DEST}/tools/kantra/"

# go-enry
if [ ! -f /usr/local/bin/go-enry ]; then
  echo "Error: /usr/local/bin/go-enry not found."
  exit 1
fi
mkdir -p "${DEST}/tools/go-enry"
echo "Copying go-enry..."
cp /usr/local/bin/go-enry "${DEST}/tools/go-enry/"

# lizard (does not fail if missing)
mkdir -p "${DEST}/tools/lizard"
if [ -f /usr/local/bin/lizard ]; then
  echo "Copying lizard..."
  cp /usr/local/bin/lizard "${DEST}/tools/lizard/"
fi
if [ ! -f /usr/local/bin/lizard ]; then
  echo "Warning: lizard CLI not found. Please install via: pip install lizard"
fi

# semgrep (does not fail if missing)
mkdir -p "${DEST}/tools/semgrep"
if [ -f /usr/local/bin/semgrep ]; then
  echo "Copying semgrep..."
  cp /usr/local/bin/semgrep "${DEST}/tools/semgrep/"
fi
if [ ! -f /usr/local/bin/semgrep ]; then
  echo "Warning: semgrep CLI not found. Please install via: pip install semgrep"
fi
if [ ! -d /root/tools/semgrep/semgrep-rules ]; then
  echo "Error: /root/tools/semgrep/semgrep-rules not found."
  exit 1
fi
echo "Copying semgrep rules..."
cp -r /root/tools/semgrep/semgrep-rules "${DEST}/tools/semgrep/"

# grype (CLI + config + db)
if [ ! -f /usr/local/bin/grype ]; then
  echo "Error: /usr/local/bin/grype not found."
  exit 1
fi
mkdir -p "${DEST}/tools/grype"
echo "Copying grype CLI..."
cp /usr/local/bin/grype "${DEST}/tools/grype/"

if [ ! -f /root/tools/.grype/config.yaml ]; then
  echo "Error: /root/tools/.grype/config.yaml not found."
  exit 1
fi
if [ ! -f /root/tools/.grype/listing.json ]; then
  echo "Error: /root/tools/.grype/listing.json not found."
  exit 1
fi
if [ ! -d /root/.grype/5 ]; then
  echo "Error: /root/.grype/5 not found."
  exit 1
fi
echo "Copying grype config..."
cp /root/tools/.grype/config.yaml "${DEST}/tools/grype/"
cp /root/tools/.grype/listing.json "${DEST}/tools/grype/"
echo "Copying grype DB..."
cp -r /root/.grype/5 "${DEST}/tools/grype/"

# syft (CLI + config)
if [ ! -f /usr/local/bin/syft ]; then
  echo "Error: /usr/local/bin/syft not found."
  exit 1
fi
mkdir -p "${DEST}/tools/syft"
echo "Copying syft CLI..."
cp /usr/local/bin/syft "${DEST}/tools/syft/"

if [ ! -f /root/tools/.syft/config.yaml ]; then
  echo "Error: /root/tools/.syft/config.yaml not found."
  exit 1
fi
echo "Copying syft config..."
cp /root/tools/.syft/config.yaml "${DEST}/tools/syft/"

# trivy
if [ ! -f /usr/local/bin/trivy ]; then
  echo "Error: /usr/local/bin/trivy not found."
  exit 1
fi
mkdir -p "${DEST}/tools/trivy"
echo "Copying trivy..."
cp /usr/local/bin/trivy "${DEST}/tools/trivy/"

if [ ! -d /root/.cache/trivy/db ]; then
  echo "Error: /root/.cache/trivy/db directory not found."
  exit 1
fi
echo "Copying trivy DB..."
cp -r /root/.cache/trivy/db "${DEST}/tools/trivy/"

echo "Done."
