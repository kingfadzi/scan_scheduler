#!/bin/bash
set -ex  # Debug: print each command as it runs

# Ensure this script is run as root.
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root (or via sudo)."
    exit 1
fi

# --- Environment Variables ---
GRADLE_VERSIONS=("4.10.3" "5.6.4" "6.9.4" "7.6.1" "8.8" "8.12")
DEFAULT_GRADLE_VERSION="8.12"
GO_VERSION="1.22.12"
GO_TARBALL="go${GO_VERSION}.linux-amd64.tar.gz"
GO_URL="https://go.dev/dl/${GO_TARBALL}"
TOOLS_URL="http://192.168.1.188/tools.tar.gz"
PREFECT_API_URL="http://192.168.1.188:4200/api"

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

# --- Install Golang ---
echo "Installing Golang ${GO_VERSION}..."
rm -f "/tmp/${GO_TARBALL}"
wget --verbose --timeout=30 --tries=3 "${GO_URL}" -O "/tmp/${GO_TARBALL}" || {
    echo "Failed to download Golang tarball from ${GO_URL}"
    exit 1
}
if [ ! -s "/tmp/${GO_TARBALL}" ]; then
    echo "Error: Downloaded Golang tarball is missing or empty."
    exit 1
fi
ls -la "/tmp/${GO_TARBALL}"
rm -rf /usr/local/go
tar -xzvf "/tmp/${GO_TARBALL}" -C /usr/local
rm "/tmp/${GO_TARBALL}"

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

if [ -d "$TEMP_SYS_EXTRACT/usr" ]; then
    echo "Copying system tools to root filesystem..."
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
rm -f /tmp/tools.tar.gz

# --- Install Yarn ---
npm install -g yarn

echo "Root setup complete."
