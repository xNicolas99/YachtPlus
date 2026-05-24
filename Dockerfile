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

# Create directories and set permissions for appuser
# Nginx directories: /var/cache/nginx, /var/log/nginx, /var/lib/nginx, /etc/nginx, /var/run/nginx
# App directories: /config, /var/www/client_body_temp, /var/www/proxy_temp
RUN mkdir -p /config /var/www/client_body_temp /var/www/proxy_temp /var/run/nginx /var/cache/nginx /var/log/nginx /var/lib/nginx /etc/nginx/conf.d && \
    chown -R appuser:appuser /config /var/www /var/log/nginx /var/lib/nginx /etc/nginx /var/run/nginx /var/cache/nginx /api

# Copy the backend code with correct ownership
COPY --chown=appuser:appuser ./backend/ ./

# Copy frontend build artifacts with correct ownership
COPY --from=build-stage --chown=appuser:appuser /app/dist /app

# Copy nginx config (global config needs to be readable by nginx master process, usually root starts it but we run as appuser? No, we run as appuser.)
# If we run nginx as appuser, the config file must be readable.
COPY --chown=appuser:appuser nginx.conf /etc/nginx/nginx.conf

# Expose ports
EXPOSE 8080

# Start script
COPY --chown=appuser:appuser backend/start.sh /start.sh
RUN chmod +x /start.sh

# Run as root (start.sh handles dropping privileges)
USER root
CMD ["/start.sh"]
