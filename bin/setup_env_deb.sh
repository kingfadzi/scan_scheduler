#!/bin/bash
set -e

# Configuration variables
export PREFECT_VERSION="3.2.1"
export PREFECT_HOME="$HOME"  # Now points directly to user's home
GRADLE_VERSIONS=("4.10.3" "5.6.4" "6.9.4" "7.6.1" "8.8" "8.12")
DEFAULT_GRADLE_VERSION="8.12"
GRADLE_BASE_URL="https://services.gradle.org/distributions/"
TOOLS_URL="http://192.168.1.188/tools.tar.gz"
GO_VERSION="1.22"

# Check for Ubuntu
if ! grep -q 'Ubuntu' /etc/os-release; then
    echo "Error: This script requires Ubuntu" >&2
    exit 1
fi

# Ensure system default Python remains the distro default (likely Python 3.10)
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 10
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
sudo apt-get update
sudo apt-get install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa

# Install system packages including Python 3.11 and its libraries.
# Note: "golang-go" is removed because we'll install Golang manually.
sudo apt-get install -y \
    nodejs npm \
    python3.11 python3.11-dev python3.11-venv \
    git wget curl unzip \
    openjdk-8-jdk openjdk-11-jdk openjdk-17-jdk openjdk-21-jdk \
    maven build-essential libssl-dev libffi-dev \
    libpq-dev python3-distutils

# Install Golang 1.22 manually
echo "Installing Golang ${GO_VERSION}..."
GO_TARBALL="go${GO_VERSION}.linux-amd64.tar.gz"
wget -q "https://go.dev/dl/${GO_TARBALL}" -O /tmp/${GO_TARBALL}
sudo rm -rf /usr/local/go
sudo tar -C /usr/local -xzf /tmp/${GO_TARBALL}
rm /tmp/${GO_TARBALL}

# Install the latest pip for Python 3.11 (accessible as python3.11)
curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11

# Java configuration
sudo update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-8-openjdk-amd64/jre/bin/java 1080
sudo update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-11-openjdk-amd64/bin/java 1110
sudo update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-17-openjdk-amd64/bin/java 1170
sudo update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-21-openjdk-amd64/bin/java 1210
sudo update-alternatives --set java /usr/lib/jvm/java-17-openjdk-amd64/bin/java

# Append environment variables to ~/.bashrc
cat << 'EOF' >> ~/.bashrc
export JAVA_8_HOME="/usr/lib/jvm/java-8-openjdk-amd64"
export JAVA_11_HOME="/usr/lib/jvm/java-11-openjdk-amd64"
export JAVA_17_HOME="/usr/lib/jvm/java-17-openjdk-amd64"
export JAVA_21_HOME="/usr/lib/jvm/java-21-openjdk-amd64"
export JAVA_HOME="$JAVA_17_HOME"
export GRADLE_HOME="/opt/gradle/gradle-8.12"
export PATH="/usr/local/go/bin:$JAVA_HOME/bin:$GRADLE_HOME/bin:$PATH"
export PREFECT_HOME="$HOME"
export PYTHONIOENCODING=utf-8
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
EOF

# Install Gradle versions
sudo mkdir -p /opt/gradle
for VERSION in "${GRADLE_VERSIONS[@]}"; do
    echo "Installing Gradle $VERSION..."
    wget -q "${GRADLE_BASE_URL}gradle-${VERSION}-bin.zip" -P /tmp
    sudo unzip -qo "/tmp/gradle-${VERSION}-bin.zip" -d /opt/gradle
    sudo ln -sf "/opt/gradle/gradle-${VERSION}/bin/gradle" "/usr/local/bin/gradle-${VERSION}"
    rm "/tmp/gradle-${VERSION}-bin.zip"
done

# Setup directories in user's home
mkdir -p "$PREFECT_HOME"/{cloned_repositories,output,logs,.ssh,.m2,.gradle,.cache,.grype,.kantra,.semgrep,.trivy,.syft}
chmod 700 "$PREFECT_HOME/.ssh"
chmod 755 "$PREFECT_HOME/.m2" "$PREFECT_HOME/.gradle"

# Handle tools tarball
echo "Downloading and installing tools..."
wget --progress=dot:giga -O /tmp/tools.tar.gz "$TOOLS_URL" || { echo "Failed to download tools"; exit 1; }

# Extract user-specific tools directly to home directory
echo "Extracting user tools to $HOME..."
tar -xzf /tmp/tools.tar.gz -C "$HOME" --strip-components=2 home/prefect

# Extract system tools to /usr
echo "Installing system tools to /usr..."
sudo tar -xzf /tmp/tools.tar.gz -C / usr

# Set permissions for system binaries
echo "Setting execute permissions..."
sudo chmod -R +x /usr/local/bin

# Cleanup
rm /tmp/tools.tar.gz

# Install Yarn
sudo npm install -g yarn

# Source the updated bashrc so that env vars are available in the current shell
source ~/.bashrc
echo "Environment variables have been updated from ~/.bashrc"
echo "Setup complete! Please restart your shell if the new environment variables do not take effect."