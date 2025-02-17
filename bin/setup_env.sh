#!/bin/bash
set -ex  # Enable debugging (prints each command)

# Configuration variables
export PREFECT_VERSION="3.2.1"
export PREFECT_HOME="$HOME"  # Points directly to user's home
GRADLE_VERSIONS=("4.10.3" "5.6.4" "6.9.4" "7.6.1" "8.8" "8.12")
DEFAULT_GRADLE_VERSION="8.12"
GRADLE_BASE_URL="https://services.gradle.org/distributions/"
TOOLS_URL="http://192.168.1.188/tools.tar.gz"
GO_VERSION="1.22.12"
GO_TARBALL="go${GO_VERSION}.linux-amd64.tar.gz"
GO_URL="https://go.dev/dl/${GO_TARBALL}"
PREFECT_API_URL="http://192.168.1.188:4200/api"
RULESETS_GIT_URL="git@github.com:kingfadzi/custom-rulesets.git"

# Check for Fedora, AlmaLinux, CentOS, or RHEL
if ! grep -E -q 'Fedora|AlmaLinux|CentOS|Red Hat Enterprise Linux' /etc/os-release; then
    echo "Error: This script requires Fedora, AlmaLinux, CentOS, or RHEL" >&2
    exit 1
fi

sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 10
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 20
sudo update-alternatives --set python3 /usr/bin/python3.10

# Configure pip
mkdir -p ~/.pip
if [[ -n "$GLOBAL_INDEX" || -n "$GLOBAL_INDEX_URL" ]]; then
    echo "[global]" > ~/.pip/pip.conf
    [ -n "$GLOBAL_INDEX" ] && echo "index = $GLOBAL_INDEX" >> ~/.pip/pip.conf
    [ -n "$GLOBAL_INDEX_URL" ] && echo "index-url = $GLOBAL_INDEX_URL" >> ~/.pip/pip.conf
    [ -n "$GLOBAL_CERT" ] && echo "cert = $GLOBAL_CERT" >> ~/.pip/pip.conf
fi

# Update system and install prerequisites
sudo dnf update -y

# Install Development Tools group and other prerequisites
sudo dnf groupinstall -y "Development Tools"
sudo dnf install -y \
    nodejs npm \
    python3.11 python3.11-devel \
    git wget curl unzip \
    java-1.8.0-openjdk-devel java-11-openjdk-devel java-17-openjdk-devel \
    # java-21-openjdk-devel \
    maven openssl-devel libffi-devel postgresql-devel

# ----- Install Golang 1.22.12 with Verbose Debugging -----
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
sudo rm -rf /usr/local/go

echo "Extracting Golang tarball to /usr/local..."
sudo tar -xzvf "/tmp/${GO_TARBALL}" -C /usr/local

echo "Golang installation complete."
rm "/tmp/${GO_TARBALL}"
# ----- End Golang Installation -----

# Install pip for Python 3.11 using dnf
sudo dnf install -y python3-pip

# Java configuration using update-alternatives
# (Ensure these paths match your installed JDK locations)
sudo update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-1.8.0-openjdk/bin/java 1080
sudo update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-11-openjdk/bin/java 1110
sudo update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-17-openjdk/bin/java 1170
sudo update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-21-openjdk/bin/java 1210
sudo update-alternatives --set java /usr/lib/jvm/java-17-openjdk/bin/java

# Append environment variables to ~/.bashrc
cat << EOF > ~/.env_variables
export JAVA_8_HOME="/usr/lib/jvm/java-1.8.0-openjdk"
export JAVA_11_HOME="/usr/lib/jvm/java-11-openjdk"
export JAVA_17_HOME="/usr/lib/jvm/java-17-openjdk"
export JAVA_21_HOME="/usr/lib/jvm/java-21-openjdk"
export JAVA_HOME="\$JAVA_17_HOME"
export GRADLE_HOME="/opt/gradle/gradle-8.12"
export PATH="/usr/local/go/bin:\$JAVA_HOME/bin:\$GRADLE_HOME/bin:\$PATH"
export PREFECT_HOME="\$HOME"
export PREFECT_API_URL="$PREFECT_API_URL"
export PYTHONIOENCODING=utf-8
export RULESETS_GIT_URL=$RULESETS_GIT_URL
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
EOF

# Install Gradle versions
sudo mkdir -p /opt/gradle
for VERSION in "${GRADLE_VERSIONS[@]}"; do
    echo "Installing Gradle $VERSION..."
    wget --progress=dot:giga "${GRADLE_BASE_URL}gradle-${VERSION}-bin.zip" -P /tmp
    sudo unzip -qo "/tmp/gradle-${VERSION}-bin.zip" -d /opt/gradle
    sudo ln -sf "/opt/gradle/gradle-${VERSION}/bin/gradle" "/usr/local/bin/gradle-${VERSION}"
    rm "/tmp/gradle-${VERSION}-bin.zip"
done

# Setup directories in user's home
mkdir -p "$PREFECT_HOME"/{cloned_repositories,output,logs,.ssh,.m2,.gradle,.cache,.grype,.kantra,.semgrep,.trivy,.syft}
chmod 700 "$PREFECT_HOME/.ssh"
if ! chmod 755 "$PREFECT_HOME/.m2"; then
    echo "Warning: Could not change permissions on $PREFECT_HOME/.m2 (possibly a mounted volume). Skipping."
fi
if ! chmod 755 "$PREFECT_HOME/.gradle"; then
    echo "Warning: Could not change permissions on $PREFECT_HOME/.gradle (possibly a mounted volume). Skipping."
fi

# ----- Handle Tools Tarball with Verbose Debugging -----
echo "Starting tools tarball handling with verbose debugging."

echo "Downloading tools tarball from $TOOLS_URL..."
wget --progress=dot:giga -O /tmp/tools.tar.gz "$TOOLS_URL" || { echo "Failed to download tools"; exit 1; }

echo "Verifying downloaded file /tmp/tools.tar.gz:"
ls -la /tmp/tools.tar.gz

echo "Listing contents of the tarball:"
tar -tzf /tmp/tools.tar.gz | tee /tmp/tools_tarball_contents.txt

# Create a temporary directory for user-specific tools extraction
TEMP_USER_EXTRACT="/tmp/tools_extracted_user"
rm -rf "$TEMP_USER_EXTRACT"
mkdir -p "$TEMP_USER_EXTRACT"

echo "Extracting tools tarball to temporary directory $TEMP_USER_EXTRACT..."
tar -xzvf /tmp/tools.tar.gz -C "$TEMP_USER_EXTRACT"

rm -rf "$HOME/.semgrep/"
rm -rf "$HOME/.kantra/"

if [ -d "$TEMP_USER_EXTRACT/home/prefect" ]; then
    echo "Copying hidden user-specific directories from $TEMP_USER_EXTRACT/home/prefect to $HOME..."
    cp -a "$TEMP_USER_EXTRACT/home/prefect/." "$HOME"
else
    echo "Error: Expected directory $TEMP_USER_EXTRACT/home/prefect not found in extracted tarball."
    exit 1
fi

echo "Listing contents of $HOME after copying user tools:"
ls -la "$HOME"

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
    sudo cp -a "$TEMP_SYS_EXTRACT/usr/." "/"
else
    echo "Error: Expected directory $TEMP_SYS_EXTRACT/usr not found in extracted tarball."
    exit 1
fi

echo "Listing contents of / after copying system tools:"
sudo ls -la /

rm -rf "$TEMP_SYS_EXTRACT"

echo "Setting execute permissions on /usr/local/bin..."
sudo chmod -R +x /usr/local/bin

echo "Removing tools tarball /tmp/tools.tar.gz..."
rm /tmp/tools.tar.gz
# ----- End Tools Tarball Handling -----

# Install Yarn
sudo npm install -g yarn

rm -rf "$PREFECT_HOME/.kantra/custom-rulesets"
if ! git clone "$RULESETS_GIT_URL" "$PREFECT_HOME/.kantra/custom-rulesets"; then
    echo "ERROR: Failed cloning rulesets from $RULESETS_GIT_URL"
    exit 1
fi

# Source the updated bashrc so environment variables are set for the current shell
source ~/.bashrc
echo "Environment variables have been updated from ~/.bashrc"
echo "Setup complete! Please restart your shell if the new environment variables do not take effect."
