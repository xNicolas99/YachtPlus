# Build Vue.js frontend
FROM node:20-alpine AS build-stage

ARG VITE_VERSION
ENV VITE_VERSION=${VITE_VERSION}

WORKDIR /app
COPY ./frontend/package*.json ./

# DEBUG STEPS
RUN node -v && npm -v
RUN npm ci --include=dev || npm install --include=dev

COPY ./frontend/ ./

# Verify structure before build
RUN ls -la

RUN npm run build --verbose

# Build Python wheels in a dedicated stage so C extensions and the
# compiler toolchain don't bloat the final runtime image.
FROM python:3.11-slim AS python-deps

WORKDIR /deps

# Install build dependencies and system libraries needed to compile packages.
RUN apt-get update && apt-get install -y --no-install-recommends     build-essential     python3-dev     default-libmysqlclient-dev     pkg-config     ca-certificates     && rm -rf /var/lib/apt/lists/*

COPY ./backend/requirements.txt ./
RUN pip install --upgrade pip setuptools wheel &&     pip wheel --no-cache-dir --wheel-dir /deps/wheels -r requirements.txt

# Setup Container and install FastAPI backend
FROM python:3.11-slim AS deploy-stage

# Set environment variables
ENV PYTHONIOENCODING=UTF-8
ENV THEME=Default

# Create user 'appuser' (UID 1000) early to use for COPY permissions.
# Give it a real $HOME — gunicorn 26's control server writes a socket
# into HOME at startup, and without it you get `Control server error:
# [Errno 13] Permission denied: '/home/appuser'` on every boot (the
# workers still run, but it spams the log and prevents the control
# socket from coming up).
RUN groupadd -r appuser -g 1000 && \
    useradd -u 1000 -r -g appuser -s /bin/bash -m -d /home/appuser -c "App User" appuser && \
    chown -R 1000:1000 /home/appuser

WORKDIR /api

# Install build dependencies and system libraries
# Switching to apt-get for Debian Slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    default-libmysqlclient-dev \
    pkg-config \
    nginx \
    curl \
    procps \
    gosu \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install the Docker CLI and the Compose v2 plugin. The backend calls
# `docker compose` (plugin form), which requires the real Docker CLI plus the
# plugin in /usr/local/lib/docker/cli-plugins. The previous build symlinked
# `/usr/local/bin/docker` directly to the Compose binary, causing
# `unknown docker command: "compose compose"`.
# Architecture: download.docker.com only publishes static docker tgz for
# x86_64 and aarch64 under the generic path used below. For other architectures
# the build would need an alternative Docker CLI source.
ARG TARGETARCH
ARG DOCKER_VERSION=27.1.2
ARG COMPOSE_VERSION=2.29.1
RUN set -eux; \
    mkdir -p /usr/local/lib/docker/cli-plugins; \
    case "${TARGETARCH}" in \
        amd64)  docker_arch=x86_64 ;; \
        arm64)  docker_arch=aarch64 ;; \
        *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL --retry 5 --retry-all-errors --retry-delay 5 \
        "https://download.docker.com/linux/static/stable/${docker_arch}/docker-${DOCKER_VERSION}.tgz" \
        -o /tmp/docker.tgz && \
    tar -xzf /tmp/docker.tgz -C /tmp && \
    mv /tmp/docker/docker /usr/local/bin/docker && \
    chmod +x /usr/local/bin/docker && \
    rm -rf /tmp/docker /tmp/docker.tgz && \
    curl -fsSL --retry 5 --retry-all-errors --retry-delay 5 \
        "https://github.com/docker/compose/releases/download/v${COMPOSE_VERSION}/docker-compose-linux-${docker_arch}" \
        -o /usr/local/lib/docker/cli-plugins/docker-compose && \
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Install pre-built wheels from the python-deps stage. This keeps the
# deploy image free of compilers and build headers.
RUN pip3 install --upgrade pip setuptools wheel &&     pip3 install --no-cache --no-index --find-links=/deps/wheels -r /deps/requirements.txt

# Create directories and set permissions for appuser. Pre-create the
# scratch dirs nginx.conf points at — Dockerfile bake-time chown is more
# reliable than runtime mkdir on overlay storage drivers that are tight
# on inodes / quota (`mkdir() ... failed: ENOSPC` was the production
# crashloop). We also create /var/lib/nginx/body for nginx versions that
# fall back to it before reading the new http-block temp_path directives.
RUN mkdir -p /config \
        /var/www/client_body_temp /var/www/proxy_temp \
        /var/www/fastcgi_temp /var/www/uwsgi_temp /var/www/scgi_temp \
        /var/run/nginx /var/cache/nginx /var/log/nginx \
        /var/lib/nginx /var/lib/nginx/body /var/lib/nginx/tmp \
        /etc/nginx/conf.d && \
    chown -R appuser:appuser /config /var/www /var/log/nginx /var/lib/nginx /etc/nginx /var/run/nginx /var/cache/nginx /api

# Copy pre-built wheels and the requirements manifest from the
# python-deps stage, then copy the backend code.
COPY --from=python-deps /deps/requirements.txt /deps/requirements.txt
COPY --from=python-deps /deps/wheels /deps/wheels

# Copy the backend code with correct ownership
COPY --chown=appuser:appuser ./backend/ ./

# Copy frontend build artifacts with correct ownership
COPY --from=build-stage --chown=appuser:appuser /app/dist /app

# Copy nginx config (global config needs to be readable by nginx master process, usually root starts it but we run as appuser? No, we run as appuser.)
# If we run nginx as appuser, the config file must be readable.
COPY --chown=appuser:appuser nginx.conf /etc/nginx/nginx.conf

# Ship the built-in app catalogs (configs/*.json). init_templates() scans
# this directory on first setup-finalize and imports every JSON file as
# a catalog, so a fresh install lands on a populated Templates page
# even when the box is offline (no GitHub fetch needed).
COPY --chown=appuser:appuser configs/ /api/configs/

# Expose ports
EXPOSE 8080

# Start script
COPY --chown=appuser:appuser backend/start.sh /start.sh
RUN chmod +x /start.sh

# Run as root (start.sh handles dropping privileges)
USER root
CMD ["/start.sh"]
