#!/bin/bash
set -ex  # Print each command for debugging

# This script must be run as your normal (non-root) user.
if [ "$EUID" -eq 0 ]; then
    echo "Error: Please run this script as a non-root user."
    exit 1
fi

# --- Environment Variables ---
# Set PREFECT_HOME to the user's home directory.
export PREFECT_HOME="$HOME"
export PREFECT_VERSION="3.2.1"
RULESETS_GIT_URL="git@github.com:kingfadzi/custom-rulesets.git"
TOOLS_URL="http://192.168.1.188/tools.tar.gz"

# --- User pip Configuration ---
mkdir -p "$HOME/.pip"
if [[ -n "$GLOBAL_INDEX" || -n "$GLOBAL_INDEX_URL" ]]; then
    cat <<EOF > "$HOME/.pip/pip.conf"
[global]
$( [ -n "$GLOBAL_INDEX" ] && echo "index = $GLOBAL_INDEX" )
$( [ -n "$GLOBAL_INDEX_URL" ] && echo "index-url = $GLOBAL_INDEX_URL" )
$( [ -n "$GLOBAL_CERT" ] && echo "cert = $GLOBAL_CERT" )
EOF
fi

# --- Create Needed Directories in Your Home ---
mkdir -p "$HOME"/{cloned_repositories,output,logs,.ssh,.m2,.gradle,.cache,.grype,.kantra,.semgrep,.trivy,.syft}
chmod 700 "$HOME/.ssh"
chmod 755 "$HOME/.m2" 2>/dev/null || echo "Warning: Could not change permissions on .m2 (possibly a mounted volume)."
chmod 755 "$HOME/.gradle" 2>/dev/null || echo "Warning: Could not change permissions on .gradle (possibly a mounted volume)."

# --- Write Environment Variables to File ---
cat <<EOF > "$HOME/.env_variables"
export PREFECT_HOME="$HOME"
export PREFECT_VERSION="$PREFECT_VERSION"
export PATH="/usr/local/go/bin:\$PATH"
EOF

# --- Download & Extract User Tools from Tarball ---
echo "Downloading tools tarball from ${TOOLS_URL}..."
wget --progress=dot:giga -O /tmp/tools.tar.gz "$TOOLS_URL" || { echo "Failed to download tools tarball"; exit 1; }

TEMP_USER_EXTRACT="/tmp/tools_extracted_user"
rm -rf "$TEMP_USER_EXTRACT"
mkdir -p "$TEMP_USER_EXTRACT"

echo "Extracting tools tarball for user-specific files..."
tar -xzvf /tmp/tools.tar.gz -C "$TEMP_USER_EXTRACT"

# Remove old copies to avoid merging stale data.
rm -rf "$HOME/.semgrep/" "$HOME/.kantra/"

if [ -d "$TEMP_USER_EXTRACT/home/prefect" ]; then
    echo "Copying user-specific directories to $HOME..."
    cp -a "$TEMP_USER_EXTRACT/home/prefect/." "$HOME"
else
    echo "Error: Expected directory $TEMP_USER_EXTRACT/home/prefect not found in the tarball."
    exit 1
fi

echo "User home after copying tools:"
ls -la "$HOME"

rm -rf "$TEMP_USER_EXTRACT"
# Optionally remove the tarball if no longer needed:
# rm /tmp/tools.tar.gz

# --- Clone the Repository (User Action) ---
CLONE_DIR="$HOME/.kantra/custom-rulesets"
echo "Cloning repository to ${CLONE_DIR}..."
SSH_KEY="$HOME/.ssh/id_ed25519"
if [ ! -f "$SSH_KEY" ]; then
    echo "Warning: SSH key $SSH_KEY not found. Cloning might fail."
fi
GIT_SSH_COMMAND="ssh -i $SSH_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes" \
git clone "$RULESETS_GIT_URL" "$CLONE_DIR" || { echo "ERROR: Failed to clone repository."; exit 1; }
echo "Repository cloned successfully to ${CLONE_DIR}"

echo "User setup complete."
