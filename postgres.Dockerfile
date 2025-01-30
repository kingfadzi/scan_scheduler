FROM almalinux:8

# Set environment variables
ENV POSTGRES_VERSION=13
ENV PGDATA=/var/lib/pgsql/data

# Accept UID and GID as build arguments
ARG USER_ID=1000
ARG GROUP_ID=1000

# Install PostgreSQL
RUN dnf -y update && \
    dnf -y install dnf-plugins-core && \
    dnf -y module enable postgresql:${POSTGRES_VERSION} && \
    dnf -y install postgresql-server postgresql-contrib && \
    dnf clean all

# Ensure the postgres group exists
RUN getent group postgres || groupadd -g ${GROUP_ID} postgres

# Ensure the postgres user exists
RUN getent passwd postgres || useradd -u ${USER_ID} -g postgres -d /var/lib/pgsql postgres

# Update UID and GID if necessary
RUN getent group postgres | grep -q ":${GROUP_ID}$" || groupmod -g ${GROUP_ID} postgres && \
    getent passwd postgres | grep -q ":${USER_ID}:" || usermod -u ${USER_ID} postgres && \
    mkdir -p ${PGDATA} && \
    chown -R postgres:postgres /var/lib/pgsql && \
    chmod 700 ${PGDATA}


# Ensure /var/run/postgresql exists with proper permissions
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
