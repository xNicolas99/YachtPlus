#!/bin/sh
set -e

# Hardened Start Script
# Runs Nginx and Gunicorn as the current user (appuser).
# Logs are directed to stdout/stderr.

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
