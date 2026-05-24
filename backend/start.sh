#!/bin/bash
set -e

# Hardened Start Script
# Runs Nginx and Gunicorn as the current user (appuser).
# Logs are directed to stdout/stderr.

# --- PERMISSION FIX (RUNS AS ROOT) ---
echo "Setting permissions..."

# 1. Ensure config directory exists and is writable
mkdir -p /config
if [ ! -f /config/yacht.db ]; then
    touch /config/yacht.db
fi

# 2. Fix ownership (Crucial for the "Permission Denied" crash)
chown -R 1000:1000 /config

# 3. Setup Nginx Logs (Crucial for Nginx crash)
mkdir -p /var/log/nginx
touch /var/log/nginx/access.log /var/log/nginx/error.log
chown -R 1000:1000 /var/log/nginx

# Also ensure other app directories are writable if they were mounted incorrectly
chown -R 1000:1000 /app /api

# Belt-and-braces: older images may have been built without /home/appuser.
# Gunicorn 26's control server writes a socket into $HOME; without this,
# you see `Control server error: [Errno 13] Permission denied: '/home/appuser'`
# in every boot log (workers run, but the control socket never comes up).
mkdir -p /home/appuser
chown 1000:1000 /home/appuser

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
