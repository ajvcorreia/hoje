#!/bin/sh
# "api" (default): apply migrations, then serve. Anything else is exec'd as given
# (e.g. the worker: python -m hoje.worker).
set -eu

if [ "${1:-api}" = "api" ]; then
    python -m hoje.migrate
    exec uvicorn hoje.main:app --host 0.0.0.0 --port 8000 \
        --proxy-headers --forwarded-allow-ips='*'
fi

exec "$@"
