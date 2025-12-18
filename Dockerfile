# Build Vue.js frontend
FROM node:16-alpine as build-stage

ARG VUE_APP_VERSION
ENV VUE_APP_VERSION=${VUE_APP_VERSION}

WORKDIR /app
COPY ./frontend/package*.json ./
RUN npm install --legacy-peer-deps --verbose
COPY ./frontend/ ./
RUN npm run build --verbose

# Setup Container and install Flask backend
FROM python:3.11-slim as deploy-stage

# Set environment variables
ENV PYTHONIOENCODING=UTF-8
ENV THEME=Default

WORKDIR /api
COPY ./backend/requirements.txt ./

# Install build dependencies and system libraries
# Switching to apt-get for Debian Slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    default-libmysqlclient-dev \
    pkg-config \
    nginx \
    curl \
    ruby-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Docker Compose 2.x as a standalone binary
# Using v2.29.1
RUN curl --retry 5 --retry-all-errors --retry-delay 5 -L "https://github.com/docker/compose/releases/download/v2.29.1/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose && \
    chmod +x /usr/local/bin/docker-compose

# Upgrade pip, setuptools, and wheel
RUN pip3 install --upgrade pip setuptools wheel

# Install Python packages from requirements.txt
RUN pip3 install -r requirements.txt --no-cache-dir --verbose

# Install SASS via gem
RUN gem install sass --verbose

# Copy the backend code
COPY ./backend/ ./

# Copy frontend build artifacts
COPY --from=build-stage /app/dist /app

# Copy nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Expose ports
EXPOSE 8000

# Create user and group 'abc' for Nginx
# On Debian, addgroup/adduser syntax differs slightly from Alpine but this should work or be adapted
RUN groupadd -r abc && useradd -r -g abc abc

# Create Nginx temp directories and set permissions
RUN mkdir -p /var/www/client_body_temp /var/www/proxy_temp && \
    chown -R abc:abc /var/www

# Start script
COPY backend/start.sh /start.sh
RUN chmod +x /start.sh

CMD ["/start.sh"]
