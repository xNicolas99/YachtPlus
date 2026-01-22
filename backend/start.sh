#!/bin/sh
set -e

# Hardened Start Script
# Runs Nginx and Gunicorn as the current user (appuser).
# Logs are directed to stdout/stderr.

# --- PERMISSION FIX (RUNS AS ROOT) ---
echo "Fixing permissions for /config..."
chown -R 1000:1000 /config

# Also ensure other app directories are writable if they were mounted incorrectly
chown -R 1000:1000 /app /api /var/lib/nginx /var/log/nginx

# Drop privileges and run the application
echo "Starting Application as appuser (UID 1000)..."

# We use 'exec gosu appuser' to switch user.
# However, we need to run multiple commands (nginx + gunicorn).
# So we run a shell as appuser to handle the logic.

exec gosu appuser /bin/bash -c '
set -e
echo "Starting Nginx..."
nginx

# Check if Nginx started correctly
sleep 2
if ! pgrep nginx > /dev/null; then
    echo "Error: Nginx failed to start!"
    exit 1
fi

echo "Starting Gunicorn..."
exec gunicorn -k uvicorn.workers.UvicornWorker \
    -w 4 \
    --bind 0.0.0.0:8000 \
    --access-logfile - \
    --error-logfile - \
    api.main:app
'
