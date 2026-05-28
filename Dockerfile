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
    && rm -rf /var/lib/apt/lists/*

# Install Docker Compose 2.x as a standalone binary
# Using v2.29.1
RUN curl --retry 5 --retry-all-errors --retry-delay 5 -L "https://github.com/docker/compose/releases/download/v2.29.1/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose && \
    chmod +x /usr/local/bin/docker-compose

# Upgrade pip, setuptools, and wheel
RUN pip3 install --upgrade pip setuptools wheel

# Copy requirements.txt first
COPY ./backend/requirements.txt ./

# Install Python packages from requirements.txt
RUN pip3 install -r requirements.txt --no-cache-dir --verbose

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
