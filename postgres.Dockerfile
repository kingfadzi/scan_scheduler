FROM almalinux:8

ENV POSTGRES_VERSION=13
ENV PGDATA=/var/lib/pgsql/data

ARG USER_ID=1000
ARG GROUP_ID=1000

RUN dnf -y update && \
    dnf -y install dnf-plugins-core && \
    dnf -y module enable postgresql:${POSTGRES_VERSION} && \
    dnf -y install postgresql-server postgresql-contrib && \
    dnf clean all

RUN getent group postgres || groupadd -g ${GROUP_ID} postgres

RUN getent passwd postgres || useradd -u ${USER_ID} -g postgres -d /var/lib/pgsql postgres

RUN getent group postgres | grep -q ":${GROUP_ID}$" || groupmod -g ${GROUP_ID} postgres && \
    getent passwd postgres | grep -q ":${USER_ID}:" || usermod -u ${USER_ID} postgres && \
    mkdir -p ${PGDATA} && \
    chown -R postgres:postgres /var/lib/pgsql && \
    chmod 700 ${PGDATA}

RUN mkdir -p /var/run/postgresql && \
    chown postgres:postgres /var/run/postgresql && \
    chmod 775 /var/run/postgresql

# Copy the entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Expose PostgreSQL port
EXPOSE 5432

# Set the entrypoint and command
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["postgres", "-D", "/var/lib/pgsql/data", "-k", "/tmp"]
