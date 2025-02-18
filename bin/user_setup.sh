#!/bin/bash
set -ex  # Print each command for debugging

# Ensure this script is run as a non-root user.
if [ "$EUID" -eq 0 ]; then
    echo "Error: Please run this script as a non-root user."
    exit 1
fi

# --- Externalize Environment Variables ---
CONFIG_FILE="./.env"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Configuration file $CONFIG_FILE not found. Aborting."
    exit 1
fi
source "$CONFIG_FILE"

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
cat << EOF > "$PREFECT_HOME/.env_variables"
export JAVA_8_HOME="/usr/lib/jvm/java-1.8.0-openjdk"
export JAVA_11_HOME="/usr/lib/jvm/java-11-openjdk"
export JAVA_17_HOME="/usr/lib/jvm/java-17-openjdk"
export JAVA_21_HOME="/usr/lib/jvm/java-21-openjdk"
export JAVA_HOME="\$JAVA_17_HOME"
export GRADLE_HOME="/opt/gradle/gradle-${DEFAULT_GRADLE_VERSION}"
export PATH="\$HOME/tools/bin:/usr/local/go/bin:\$JAVA_HOME/bin:\$GRADLE_HOME/bin:\$PATH"
export PREFECT_HOME="$PREFECT_HOME"
export PREFECT_API_URL="$PREFECT_API_URL"
export PYTHONIOENCODING=utf-8
export RULESETS_GIT_URL=$RULESETS_GIT_URL
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
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

# --- Extract tool binaries to $HOME/tools/bin ---
if [ -d "$TEMP_USER_EXTRACT/usr/local/bin" ]; then
    TARGET_BIN="$HOME/tools/bin"
    echo "Copying tool binaries to $TARGET_BIN..."
    mkdir -p "$TARGET_BIN"
    cp -a "$TEMP_USER_EXTRACT/usr/local/bin/." "$TARGET_BIN"
else
    echo "Warning: No tool binaries found in the tarball at usr/local/bin."
fi

# --- Copy user-specific directories ---
if [ -d "$TEMP_USER_EXTRACT/home/prefect" ]; then
    echo "Copying user-specific directories to $HOME..."
    cp -a "$TEMP_USER_EXTRACT/home/prefect/." "$HOME"
else
    echo "Error: Expected directory $TEMP_USER_EXTRACT/home/prefect not found in the tarball."
    exit 1
fi

echo "User home after copying tools and configuration files:"
ls -la "$HOME"

rm -rf "$TEMP_USER_EXTRACT"
# Optionally remove the tarball:
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
