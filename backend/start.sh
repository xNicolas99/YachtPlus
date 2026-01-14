#!/bin/sh
set -e

# Hardened Start Script
# Runs Nginx and Gunicorn as the current user (appuser).
# Logs are directed to stdout/stderr.

# --- PERMISSION CHECK (FAIL FAST) ---
# Ensure we can write to /config. If not, fail immediately with clear instructions.
# This handles the migration scenario where a user upgrades from Root to Non-Root
# and still has root-owned files in their volume.
if ! touch "/config/.perm_check" 2>/dev/null; then
    echo ""
    echo "################################################################################"
    echo "CRITICAL ERROR: PERMISSION DENIED"
    echo "################################################################################"
    echo ""
    echo "The container (running as uid=1000) cannot write to the /config volume."
    echo "This is likely because you are migrating from an older version where Yacht ran as 'root'."
    echo ""
    echo "REQUIRED FIX:"
    echo "Please run the following command on your host machine to fix ownership:"
    echo ""
    echo "    sudo chown -R 1000:1000 ./config"
    echo ""
    echo "Then restart the container."
    echo "################################################################################"
    echo ""
    exit 1
fi
rm "/config/.perm_check"
# ------------------------------------

echo "Starting Nginx..."
# Start Nginx in background, using the custom config that logs to stdout/stderr
nginx

# Check if Nginx started correctly
sleep 2
if ! pgrep nginx > /dev/null; then
    echo "Error: Nginx failed to start!"
    exit 1
fi

echo "Starting Application (Gunicorn)..."
# Run Gunicorn with Uvicorn workers
# -k uvicorn.workers.UvicornWorker: Use Uvicorn for asyncio support (FastAPI)
# -w 4: Number of workers (adjust based on needs, 4 is standard for small/med)
# --bind 0.0.0.0:8000: Bind to all interfaces on port 8000
# --access-logfile -: Log access to stdout
# --error-logfile -: Log errors to stderr
exec gunicorn -k uvicorn.workers.UvicornWorker \
    -w 4 \
    --bind 0.0.0.0:8000 \
    --access-logfile - \
    --error-logfile - \
    api.main:app
