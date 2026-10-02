#!/bin/sh
# Image smoke test for YachtPlus Docker builds.
# Run with: docker run --rm --entrypoint sh yachtplus:latest /scripts/image-smoke-test.sh
set -eu

echo "=== Docker CLI ==="
docker --version

echo "=== Docker Compose plugin ==="
docker compose version

echo "=== Nginx configuration and frontend bundle ==="
nginx -t
test -s /app/index.html
test -d /app/assets
test -s /app/version.json

echo "=== No packaged credentials or runtime databases ==="
packaged_files="$(find /api /config -type f \( -name '.secret_key' -o -name '.fernet_salt' -o -name '.env' -o -name '.env.*' -o -name '*.db' -o -name '*.db-*' \) -print -quit)"
test -z "$packaged_files"

echo "=== Backend import ==="
cd /api
python3 -c 'from api.main import app; assert app.title == "YachtPlus API"'

echo "OK"
