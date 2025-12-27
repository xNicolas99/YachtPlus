#!/bin/sh
set -e

# Non-Root Transition Logic
# This script must be run as root to perform permission checks and adjustments

# Detect the GID of the Docker socket
if [ -z "${DOCKER_GID}" ]; then
    if [ -S /var/run/docker.sock ]; then
        if DOCKER_GID=$(stat -c '%g' /var/run/docker.sock 2>/dev/null); then
            echo "Auto-detected DOCKER_GID: ${DOCKER_GID}"
        else
            DOCKER_GID=$(ls -n /var/run/docker.sock | awk '{print $4}')
            echo "Auto-detected DOCKER_GID (fallback): ${DOCKER_GID}"
        fi
    else
        echo "Socket not found. Defaulting DOCKER_GID to 999."
        DOCKER_GID=999
    fi
fi

# Ensure DOCKER_GID is valid
if ! echo "$DOCKER_GID" | grep -Eq '^[0-9]+$'; then
    echo "Invalid DOCKER_GID: $DOCKER_GID. Defaulting to 999."
    DOCKER_GID=999
fi

# 1. Check if the 'docker' group exists in the container
if getent group docker > /dev/null 2>&1; then
    # Group 'docker' exists. Check its GID.
    CURRENT_GID=$(getent group docker | cut -d: -f3)
    if [ "$CURRENT_GID" != "$DOCKER_GID" ]; then
        echo "Group 'docker' exists with GID $CURRENT_GID. Changing to $DOCKER_GID."
        groupmod -g ${DOCKER_GID} docker
    else
        echo "Group 'docker' already has GID ${DOCKER_GID}."
    fi
else
    # Group 'docker' does not exist.
    # Check if ANY group uses this GID.
    if getent group ${DOCKER_GID} > /dev/null 2>&1; then
        EXISTING_GROUP=$(getent group ${DOCKER_GID} | cut -d: -f1)
        echo "GID ${DOCKER_GID} is used by group '${EXISTING_GROUP}'. Renaming to 'docker'."
        groupmod -n docker ${EXISTING_GROUP}
    else
        echo "Creating group 'docker' with GID ${DOCKER_GID}."
        groupadd -g ${DOCKER_GID} docker
    fi
fi

# 2. Add appuser to the 'docker' group
echo "Adding appuser to 'docker' group."
usermod -aG docker appuser

# Set permissions for socket (just in case)
if [ -S /var/run/docker.sock ]; then
    # Ensure group read/write
    chmod 660 /var/run/docker.sock 2>/dev/null || true
fi

# Fix ownership of config directories
mkdir -p /config/compose
chown -R appuser:appuser /config
mkdir -p /var/log/nginx
chown -R appuser:appuser /var/log/nginx

# Start Nginx logic (same as before but simplified/cleaned if needed)
echo "Starting log forwarder..."
tail -F /var/log/nginx/access.log /var/log/nginx/error.log &

echo "Starting Nginx..."
gosu appuser nginx

sleep 2
if ! pgrep nginx > /dev/null; then
    echo "Error: Nginx failed to start!"
    cat /var/log/nginx/error.log
    exit 1
fi

echo "Starting Application..."
# Exec python directly as requested
exec gosu appuser python3 -m api.main
