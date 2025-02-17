#!/bin/bash
set -ex  # Enable debugging (prints each command)

# If not running as root, re‑exec using sudo with preserved environment.
if [ "$EUID" -ne 0 ]; then
    echo "Script must be run as root. Relaunching with sudo..."
    exec sudo -E "$0" "$@"
fi

# Determine the real user's home directory (if run via sudo, SUDO_USER is set)
if [ -n "$SUDO_USER" ]; then
    REAL_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
else
    REAL_HOME="$HOME"
fi

# Set environment variables (user‑specific ones will use the original user’s home)
export PREFECT_VERSION="3.2.1"
export PREFECT_HOME="$REAL_HOME"  # Use the non‑root user’s home
GRADLE_VERSIONS=("4.10.3" "5.6.4" "6.9.4" "7.6.1" "8.8" "8.12")
DEFAULT_GRADLE_VERSION="8.12"
GRADLE_BASE_URL="https://services.gradle.org/distributions/"
TOOLS_URL="http://192.168.1.188/tools.tar.gz"
GO_VERSION="1.22.12"
GO_TARBALL="go${GO_VERSION}.linux-amd64.tar.gz"
GO_URL="https://go.dev/dl/${GO_TARBALL}"
PREFECT_API_URL="http://192.168.1.188:4200/api"
RULESETS_GIT_URL="git@github.com:kingfadzi/custom-rulesets.git"
SSH_KEY="$HOME/.ssh/id_ed25519"

# Check for Fedora, AlmaLinux, CentOS, or RHEL
if ! grep -E -q 'Fedora|AlmaLinux|CentOS|Red Hat Enterprise Linux' /etc/os-release; then
    echo "Error: This script requires Fedora, AlmaLinux, CentOS, or RHEL" >&2
    exit 1
fi

# --- Python Setup ---
# Ensure system default Python remains the distro default (3.10) with python3.11 as an alternative.
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 10
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 20
update-alternatives --set python3 /usr/bin/python3.10

# Configure pip for the user (using the original user's home)
mkdir -p "$PREFECT_HOME/.pip"
if [[ -n "$GLOBAL_INDEX" || -n "$GLOBAL_INDEX_URL" ]]; then
    echo "[global]" > "$PREFECT_HOME/.pip/pip.conf"
    [ -n "$GLOBAL_INDEX" ] && echo "index = $GLOBAL_INDEX" >> "$PREFECT_HOME/.pip/pip.conf"
    [ -n "$GLOBAL_INDEX_URL" ] && echo "index-url = $GLOBAL_INDEX_URL" >> "$PREFECT_HOME/.pip/pip.conf"
    [ -n "$GLOBAL_CERT" ] && echo "cert = $GLOBAL_CERT" >> "$PREFECT_HOME/.pip/pip.conf"
fi

# --- System Update & Package Installation ---
dnf update -y

# Install Development Tools group and other prerequisites
dnf groupinstall -y "Development Tools"
dnf install -y \
    nodejs npm \
    python3.11 python3.11-devel \
    git wget curl unzip \
    java-1.8.0-openjdk-devel java-11-openjdk-devel java-17-openjdk-devel \
    maven openssl-devel libffi-devel postgresql-devel
    # Note: jdk 21 not available in Fedora 36

# --- Install Golang 1.22.12 ---
echo "Installing Golang ${GO_VERSION}..."
echo "Downloading Golang from ${GO_URL}..."
rm -f "/tmp/${GO_TARBALL}"
wget --verbose --timeout=30 --tries=3 "${GO_URL}" -O "/tmp/${GO_TARBALL}" || {
    echo "Failed to download Golang tarball from ${GO_URL}"; exit 1;
}

if [ ! -s "/tmp/${GO_TARBALL}" ]; then
    echo "Downloaded Golang tarball is missing or empty."; exit 1;
fi

echo "Golang tarball downloaded successfully. File details:"
ls -la "/tmp/${GO_TARBALL}"

echo "Removing any existing Go installation from /usr/local/go..."
rm -rf /usr/local/go

echo "Extracting Golang tarball to /usr/local..."
tar -xzvf "/tmp/${GO_TARBALL}" -C /usr/local

echo "Golang installation complete."
rm "/tmp/${GO_TARBALL}"

# --- Install pip for Python 3.11 ---
dnf install -y python3-pip

# --- Java Setup ---
# Configure Java using update-alternatives
update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-1.8.0-openjdk/bin/java 1080
update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-11-openjdk/bin/java 1110
update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-17-openjdk/bin/java 1170
update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-21-openjdk/bin/java 1210
update-alternatives --set java /usr/lib/jvm/java-17-openjdk/bin/java

# --- Environment Variables ---
# Append environment variables to a file in the original user's home
cat << EOF > "$PREFECT_HOME/.env_variables"
export JAVA_8_HOME="/usr/lib/jvm/java-1.8.0-openjdk"
export JAVA_11_HOME="/usr/lib/jvm/java-11-openjdk"
export JAVA_17_HOME="/usr/lib/jvm/java-17-openjdk"
export JAVA_21_HOME="/usr/lib/jvm/java-21-openjdk"
export JAVA_HOME="\$JAVA_17_HOME"
export GRADLE_HOME="/opt/gradle/gradle-${DEFAULT_GRADLE_VERSION}"
export PATH="/usr/local/go/bin:\$JAVA_HOME/bin:\$GRADLE_HOME/bin:\$PATH"
export PREFECT_HOME="$PREFECT_HOME"
export PREFECT_API_URL="$PREFECT_API_URL"
export PYTHONIOENCODING=utf-8
export RULESETS_GIT_URL=$RULESETS_GIT_URL
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
EOF

# --- Install Gradle Versions ---
mkdir -p /opt/gradle
for VERSION in "${GRADLE_VERSIONS[@]}"; do
    echo "Installing Gradle $VERSION..."
    wget --progress=dot:giga "${GRADLE_BASE_URL}gradle-${VERSION}-bin.zip" -P /tmp
    unzip -qo "/tmp/gradle-${VERSION}-bin.zip" -d /opt/gradle
    ln -sf "/opt/gradle/gradle-${VERSION}/bin/gradle" "/usr/local/bin/gradle-${VERSION}"
    rm "/tmp/gradle-${VERSION}-bin.zip"
done

# --- Setup Directories in the User's Home ---
mkdir -p "$PREFECT_HOME"/{cloned_repositories,output,logs,.ssh,.m2,.gradle,.cache,.grype,.kantra,.semgrep,.trivy,.syft}
chmod 700 "$PREFECT_HOME/.ssh"
if ! chmod 755 "$PREFECT_HOME/.m2"; then
    echo "Warning: Could not change permissions on $PREFECT_HOME/.m2 (possibly a mounted volume). Skipping."
fi
if ! chmod 755 "$PREFECT_HOME/.gradle"; then
    echo "Warning: Could not change permissions on $PREFECT_HOME/.gradle (possibly a mounted volume). Skipping."
fi

# --- Handle Tools Tarball ---
echo "Starting tools tarball handling with verbose debugging."

echo "Downloading tools tarball from $TOOLS_URL..."
wget --progress=dot:giga -O /tmp/tools.tar.gz "$TOOLS_URL" || { echo "Failed to download tools"; exit 1; }

#echo "Verifying downloaded file /tmp/tools.tar.gz:"
#ls -la /tmp/tools.tar.gz

#echo "Listing contents of the tarball:"
#rm -f /tmp/tools_tarball_contents.txt
#tar -tzf /tmp/tools.tar.gz | tee /tmp/tools_tarball_contents.txt

# Create a temporary directory for user-specific tools extraction
TEMP_USER_EXTRACT="/tmp/tools_extracted_user"
rm -rf "$TEMP_USER_EXTRACT"
mkdir -p "$TEMP_USER_EXTRACT"

echo "Extracting tools tarball to temporary directory $TEMP_USER_EXTRACT..."
tar -xzvf /tmp/tools.tar.gz -C "$TEMP_USER_EXTRACT"

rm -rf "$PREFECT_HOME/.semgrep/"
rm -rf "$PREFECT_HOME/.kantra/"

if [ -d "$TEMP_USER_EXTRACT/home/prefect" ]; then
    echo "Copying hidden user-specific directories from $TEMP_USER_EXTRACT/home/prefect to $PREFECT_HOME..."
    cp -a "$TEMP_USER_EXTRACT/home/prefect/." "$PREFECT_HOME"
else
    echo "Error: Expected directory $TEMP_USER_EXTRACT/home/prefect not found in extracted tarball."
    exit 1
fi

echo "Listing contents of $PREFECT_HOME after copying user tools:"
ls -la "$PREFECT_HOME"

# Remove the temporary extraction directory for user tools
rm -rf "$TEMP_USER_EXTRACT"

# Create a temporary directory for system tools extraction
TEMP_SYS_EXTRACT="/tmp/tools_extracted_sys"
rm -rf "$TEMP_SYS_EXTRACT"
mkdir -p "$TEMP_SYS_EXTRACT"

echo "Extracting system tools to temporary directory $TEMP_SYS_EXTRACT..."
tar -xzvf /tmp/tools.tar.gz -C "$TEMP_SYS_EXTRACT"

if [ -d "$TEMP_SYS_EXTRACT/usr" ]; then
    echo "Copying system tools from $TEMP_SYS_EXTRACT/usr to /..."
    cp -a "$TEMP_SYS_EXTRACT/usr/." "/"
else
    echo "Error: Expected directory $TEMP_SYS_EXTRACT/usr not found in extracted tarball."
    exit 1
fi

echo "Listing contents of /usr/local/bin after copying system tools:"
ls -la /usr/local/bin

rm -rf "$TEMP_SYS_EXTRACT"

echo "Setting execute permissions on /usr/local/bin..."
chmod -R +x /usr/local/bin

echo "Removing tools tarball /tmp/tools.tar.gz..."
rm /tmp/tools.tar.gz

# --- Install Yarn ---
npm install -g yarn

USER_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
echo "USER_HOME: $USER_HOME"

CLONE_DIR="$USER_HOME/.kantra/custom-rulesets"
echo "CLONE_DIR: $CLONE_DIR"

# Add the SSH key from the non-root user's home to the SSH agent
eval "$(ssh-agent -s)" && ssh-add "$SSH_KEY"

# Clone the repository non-interactively using the specified SSH key
export GIT_SSH_COMMAND="ssh -i $SSH_KEY -o IdentitiesOnly=yes"
rm -rf "$CLONE_DIR" && git clone "$RULESETS_GIT_URL" "$CLONE_DIR" || {
    echo "ERROR: Failed to clone $RULESETS_GIT_URL"
    exit 1
}

echo "Repository cloned successfully to $CLONE_DIR"

dockerecho "Setup complete! Please restart your shell if the new environment variables do not take effect."
