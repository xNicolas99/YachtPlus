#!/bin/sh
# Image smoke test for YachtPlus Docker builds.
# Run inside the built image or via: docker run --rm yachtplus:latest /scripts/image-smoke-test.sh
set -eu

echo "=== Docker CLI ==="
docker --version

echo "=== Docker Compose plugin ==="
docker compose version

echo "=== Compose standalone symlink ==="
test -L /usr/local/bin/docker-compose || test -x /usr/local/bin/docker-compose

echo "=== YachtPlus compose command path (from backend/api/actions/compose.py) ==="
docker compose ls 2>/dev/null || true

echo "OK"
