#!/bin/bash
set -euo pipefail

if [ "$(id -u)" != "1000" ]; then
    echo "YachtPlus must run as UID 1000 (image default)." >&2
    exit 1
fi
for directory in /config /config/security /compose /var/run/nginx /var/www /home/appuser; do
    if [ ! -d "$directory" ] || [ ! -w "$directory" ]; then
        echo "YachtPlus cannot write $directory. Stop the stack and set this mounted directory's ownership to 1000:1000, then restart." >&2
        exit 1
    fi
done
if ! touch /config/security/auth.log; then
    echo "YachtPlus cannot write /config/security/auth.log; set the log volume ownership to 1000:1000." >&2
    exit 1
fi

python /api/configure_nginx.py
export FORWARDED_ALLOW_IPS=''
echo "Applying database migrations..."
alembic upgrade head
nginx -t
nginx -g 'daemon off;' &
nginx_pid=$!
# In-memory rate limits are process-local. One worker keeps the published
# login and global limits effective; async Docker I/O remains concurrent.
gunicorn -k uvicorn.workers.UvicornWorker -w 1 \
    --bind 127.0.0.1:8000 --forwarded-allow-ips='' \
    --access-logfile - --error-logfile - api.main:app &
gunicorn_pid=$!

stop() {
    kill -TERM "$nginx_pid" "$gunicorn_pid" 2>/dev/null || true
    wait "$nginx_pid" "$gunicorn_pid" 2>/dev/null || true
}
trap stop EXIT
trap 'exit 0' TERM INT
# Stop both services if either exits: a partial app must not appear healthy.
set +e
wait -n "$nginx_pid" "$gunicorn_pid"
status=$?
set -e
exit "${status:-1}"
