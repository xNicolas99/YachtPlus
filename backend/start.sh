#!/bin/sh
set -e

# Non-Root Transition Logic
# DOCKER_GID can be passed from host (e.g. $(getent group docker | cut -d: -f3))
if [ -z "${DOCKER_GID}" ]; then
    echo "DOCKER_GID not set. Defaulting to 999 (standard docker group)."
    DOCKER_GID=999
fi

# Create or modify the docker group to match the host's GID
if ! getent group ${DOCKER_GID} > /dev/null 2>&1; then
    echo "Creating docker group with GID ${DOCKER_GID}"
    groupadd -g ${DOCKER_GID} docker_host_group
else
    # If group exists (maybe 'docker' already exists with different GID, or another group uses this GID)
    GROUP_NAME=$(getent group ${DOCKER_GID} | cut -d: -f1)
    echo "Group with GID ${DOCKER_GID} already exists: ${GROUP_NAME}"
    # If the group name is not 'docker', we might want to use it anyway.
fi

# Add appuser to the group with DOCKER_GID
# We find the group name associated with the GID
TARGET_GROUP=$(getent group ${DOCKER_GID} | cut -d: -f1)
echo "Adding appuser to group ${TARGET_GROUP}"
usermod -aG ${TARGET_GROUP} appuser

# Set permissions for /var/run/docker.sock if it exists
if [ -S /var/run/docker.sock ]; then
    # We shouldn't chown the socket as it belongs to root on host usually,
    # but inside container it appears as root:root (or root:group).
    # Since we added appuser to the group matching the socket's GID (hopefully),
    # access should work.
    echo "Docker socket found."
else
    echo "Warning: /var/run/docker.sock not found."
fi

# Create config directories if they don't exist
# We are currently root, so we should make sure they are owned by appuser
mkdir -p /config/compose
chown -R appuser:appuser /config

# Ensure Nginx log permissions and create files
mkdir -p /var/log/nginx
touch /var/log/nginx/access.log /var/log/nginx/error.log
chown -R appuser:appuser /var/log/nginx

# Switch to appuser for execution
echo "Switching to appuser..."

# Start tailing logs in the background to forward them to stdout/stderr
# We use 'gosu appuser' to ensure the tail process runs as appuser (though reading is fine as root)
# Actually, tailing as root is fine.
echo "Starting log forwarder..."
tail -F /var/log/nginx/access.log /var/log/nginx/error.log &
TAIL_PID=$!

# Start Nginx (running in background as appuser)
# Nginx is configured to listen on 8080 and use /var/run/nginx for pid
echo "Starting Nginx..."
gosu appuser nginx

# Check if Nginx started
sleep 2
if ! pgrep nginx > /dev/null; then
    echo "Error: Nginx failed to start!"
    echo "Nginx error log content:"
    cat /var/log/nginx/error.log || true
    kill $TAIL_PID
    exit 1
fi

echo "Starting Gunicorn..."
# Exec Gunicorn as appuser
# Note: This replaces the shell process, so the tail background job becomes an orphan
# (which is usually fine in Docker as init picks it up, or it dies when container dies).
exec gosu appuser gunicorn api.main:app \
    --workers 1 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind unix:/tmp/gunicorn.sock \
    --umask 000 \
    --log-level info
