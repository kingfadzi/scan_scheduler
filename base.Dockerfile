# base.Dockerfile

# FROM registry.access.redhat.com/ubi8/ubi:latest
FROM almalinux:8

ENV AIRFLOW_HOME=/home/airflow/airflow
ENV AIRFLOW_DAGS_FOLDER=/home/airflow/airflow/dags

ARG GLOBAL_INDEX
ARG GLOBAL_INDEX_URL
ARG HOST_UID=1000
ARG HOST_GID=1000
ARG GRADLE_DISTRIBUTIONS_BASE_URL="https://services.gradle.org/distributions/"
ARG GRADLE_VERSIONS="4.10.3 5.6.4 6.9.4 7.6.1 8.8 8.12"
ARG DEFAULT_GRADLE_VERSION=8.12
ARG TOOLS_TARBALL_URL="http://192.168.1.188/tools.tar.gz"

COPY keys/ /tmp/keys/

RUN if [ -f "/tmp/keys/tls-ca-bundle.pem" ]; then \
      mkdir -p /etc/ssl/certs && \
      cp /tmp/keys/tls-ca-bundle.pem /etc/ssl/certs/ && \
      echo -e "[global]\ncert = /etc/ssl/certs/tls-ca-bundle.pem" > /etc/pip.conf; \
    else \
      echo "[global]" > /etc/pip.conf; \
    fi && \
    [ -n "$GLOBAL_INDEX" ] && echo "index = ${GLOBAL_INDEX}" >> /etc/pip.conf; \
    echo "index-url = ${GLOBAL_INDEX_URL}" >> /etc/pip.conf

RUN if [ -f "/tmp/keys/java.cacerts" ]; then \
      mkdir -p /home/airflow && \
      cp /tmp/keys/java.cacerts /home/airflow/java.cacerts; \
    fi

RUN dnf -y update && \
    dnf module reset -y python36 && \
    dnf install -y \
      bash \
      nc \
      glibc-langpack-en \
      python3.11 \
      python3-pip \
      python3-devel \
      git \
      wget \
      unzip \
      dnf-plugins-core && \
    dnf module reset -y maven && \
    dnf module enable -y maven:3.8 && \
    dnf module install -y maven && \
    dnf clean all

ENV PYTHONIOENCODING=utf-8
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

RUN alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 && \
    alternatives --set python3 /usr/bin/python3.11 && \
    python3 -m ensurepip && \
    python3 -m pip install --no-cache-dir --upgrade pip && \
    python3 -m pip install --no-cache-dir \
      apache-airflow[postgres] \
      psycopg2-binary \
      gitpython \
      apache-airflow-providers-postgres \
      requests \
      pandas \
      numpy \
      lizard \
      semgrep \
      python-dotenv \
      checkov \
      sqlalchemy

RUN dnf install -y \
      java-1.8.0-openjdk-devel \
      java-11-openjdk-devel \
      java-17-openjdk-devel \
      java-21-openjdk-devel && \
    dnf clean all

RUN alternatives --install /usr/bin/java java /usr/lib/jvm/java-1.8.0/bin/java 1080 && \
    alternatives --install /usr/bin/java java /usr/lib/jvm/java-11/bin/java 1110 && \
    alternatives --install /usr/bin/java java /usr/lib/jvm/java-17/bin/java 1170 && \
    alternatives --install /usr/bin/java java /usr/lib/jvm/java-21/bin/java 1210 && \
    alternatives --set java /usr/lib/jvm/java-17/bin/java

ENV JAVA_8_HOME="/usr/lib/jvm/java-1.8.0"
ENV JAVA_11_HOME="/usr/lib/jvm/java-11"
ENV JAVA_17_HOME="/usr/lib/jvm/java-17"
ENV JAVA_21_HOME="/usr/lib/jvm/java-21"
ENV JAVA_HOME="${JAVA_17_HOME}"
ENV PATH="${JAVA_HOME}/bin:${PATH}"

RUN dnf install -y unzip wget \
 && mkdir -p /opt/gradle \
 && for VERSION in $GRADLE_VERSIONS; do \
      echo "Installing Gradle $VERSION..."; \
      wget "${GRADLE_DISTRIBUTIONS_BASE_URL}gradle-${VERSION}-bin.zip" -O /tmp/gradle-${VERSION}-bin.zip; \
      unzip -qo /tmp/gradle-${VERSION}-bin.zip -d /opt/gradle; \
      rm /tmp/gradle-${VERSION}-bin.zip; \
      ln -s "/opt/gradle/gradle-${VERSION}/bin/gradle" "/usr/local/bin/gradle-${VERSION}"; \
    done \
 && dnf clean all

ENV GRADLE_HOME="/opt/gradle/gradle-${DEFAULT_GRADLE_VERSION}"
ENV PATH="$GRADLE_HOME/bin:$PATH"

RUN existing_group=$(getent group ${HOST_GID} | cut -d: -f1) && \
    if [ -z "$existing_group" ]; then \
      groupadd -g ${HOST_GID} airflow; \
    else \
      groupmod -n airflow "$existing_group"; \
    fi && \
    existing_user=$(getent passwd ${HOST_UID} | cut -d: -f1) && \
    if [ -z "$existing_user" ]; then \
      useradd -m -u ${HOST_UID} -g airflow airflow; \
    else \
      usermod -l airflow "$existing_user"; \
    fi

RUN mkdir -p \
      /home/airflow/airflow \
      /home/airflow/airflow/cloned_repositories \
      /home/airflow/airflow/output \
      /home/airflow/.ssh && \
    chmod 700 /home/airflow/.ssh

COPY --chown=airflow:airflow ./airflow.cfg $AIRFLOW_HOME/airflow.cfg

RUN wget --progress=dot:giga -O /tmp/tools.tar.gz "${TOOLS_TARBALL_URL}" \
    || (echo "Error: Failed to download tools tarball" && exit 1) \
 && tar -xzvf /tmp/tools.tar.gz -C / \
 && rm /tmp/tools.tar.gz \
 && chown -R airflow:airflow /usr/local/bin \
 && chmod -R +x /usr/local/bin

RUN chown airflow:airflow -R /home/airflow/.cache
RUN chown airflow:airflow -R /home/airflow/.grype
RUN chown airflow:airflow -R /home/airflow/.kantra
RUN chown airflow:airflow -R /home/airflow/.semgrep
RUN chown airflow:airflow -R /home/airflow/.trivy

RUN mkdir -p /home/airflow/.pip && \
    if [ -n "$GLOBAL_CERT" ]; then \
      echo -e "[global]\ncert = ${GLOBAL_CERT}\nindex-url = ${GLOBAL_INDEX_URL}" > /home/airflow/.pip/pip.conf; \
    else \
      echo -e "[global]\nindex-url = ${GLOBAL_INDEX_URL}" > /home/airflow/.pip/pip.conf; \
    fi

USER airflow
WORKDIR /home/airflow/airflow
