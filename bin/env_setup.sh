#!/bin/bash
set -ex  # Debug: print each command as it runs

# Ensure this script is run as root.
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root (or via sudo)."
    exit 1
fi

# --- Environment Variables ---
GRADLE_VERSIONS=("4.10.3" "5.6.4" "6.9.4" "7.6.1" "8.8" "8.12")

# --- Externalize Environment Variables ---
CONFIG_FILE="./.env"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Configuration file $CONFIG_FILE not found. Aborting."
    exit 1
fi
source "$CONFIG_FILE"

# --- OS Check ---
if ! grep -E -q 'Fedora|AlmaLinux|CentOS|Red Hat Enterprise Linux' /etc/os-release; then
    echo "Error: This script requires Fedora, AlmaLinux, CentOS, or RHEL."
    exit 1
fi

# --- Python Setup ---
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 10
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 20
update-alternatives --set python3 /usr/bin/python3.10

# --- System Update & Package Installation ---
dnf update -y
dnf groupinstall -y "Development Tools"
dnf install -y \
    nodejs npm \
    python3.11 python3.11-devel \
    git wget curl unzip \
    java-1.8.0-openjdk-devel java-11-openjdk-devel java-17-openjdk-devel \
    maven openssl-devel libffi-devel postgresql-devel

# Enable the desired module stream.
if ! dnf install -y golang-$GO_VERSION; then
  echo "Error: Golang version $GO_VERSION is not available in the repositories."
  exit 1
fi


# Install Golang.
dnf install -y golang

# --- Install pip for Python 3.11 ---
dnf install -y python3-pip

# --- Java Setup ---
update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-1.8.0-openjdk/bin/java 1080
update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-11-openjdk/bin/java 1110
update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-17-openjdk/bin/java 1170
update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-21-openjdk/bin/java 1210
update-alternatives --set java /usr/lib/jvm/java-17-openjdk/bin/java

# --- Install Gradle Versions ---
mkdir -p /opt/gradle
for VERSION in "${GRADLE_VERSIONS[@]}"; do
    echo "Installing Gradle $VERSION..."
    wget --progress=dot:giga "https://services.gradle.org/distributions/gradle-${VERSION}-bin.zip" -P /tmp
    unzip -qo "/tmp/gradle-${VERSION}-bin.zip" -d /opt/gradle
    ln -sf "/opt/gradle/gradle-${VERSION}/bin/gradle" "/usr/local/bin/gradle-${VERSION}"
    rm "/tmp/gradle-${VERSION}-bin.zip"
done

# --- Extract & Install System Tools from Tarball ---
echo "Handling system tools extraction from tarball..."
if [ ! -f /tmp/tools.tar.gz ]; then
    echo "Downloading tools tarball from ${TOOLS_URL}..."
    wget --progress=dot:giga -O /tmp/tools.tar.gz "$TOOLS_URL" || { echo "Failed to download tools tarball"; exit 1; }
fi

TEMP_SYS_EXTRACT="/tmp/tools_extracted_sys"
rm -rf "$TEMP_SYS_EXTRACT"
mkdir -p "$TEMP_SYS_EXTRACT"

echo "Extracting tools tarball to $TEMP_SYS_EXTRACT..."
tar -xzvf /tmp/tools.tar.gz -C "$TEMP_SYS_EXTRACT"

if [ -d "$TEMP_SYS_EXTRACT/usr/local/bin" ]; then
    TARGET_DIR="$HOME/tools/bin"
    echo "Copying system tools to $TARGET_DIR..."
    mkdir -p "$TARGET_DIR"
    cp -a "$TEMP_SYS_EXTRACT/usr/local/bin/." "$TARGET_DIR"
else
    echo "Error: Expected directory $TEMP_SYS_EXTRACT/usr/local/bin not found in extracted tarball."
    exit 1
fi

echo "Listing contents of $TARGET_DIR after copying system tools:"
ls -la "$TARGET_DIR"

rm -rf "$TEMP_SYS_EXTRACT"
echo "Setting execute permissions on $TARGET_DIR..."
chmod -R +x "$TARGET_DIR"

echo "Removing tools tarball /tmp/tools.tar.gz..."
rm -f /tmp/tools.tar.gz

# --- Install Yarn ---
npm install -g yarn

echo "Root setup complete."
