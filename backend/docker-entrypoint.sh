#!/bin/sh
# "api" (default): apply migrations, then serve. Anything else is exec'd as given
# (e.g. the worker: python -m hoje.worker).
#
# Proxy headers are deliberately off: uvicorn would trust the left-most (client-controlled)
# X-Forwarded-For. The client address comes from X-Real-IP, which hoje-web (Caddy) overwrites;
# see hoje.api.deps.client_ip. The API must only be reachable through hoje-web.
set -eu

if [ "${1:-api}" = "api" ]; then
    python -m hoje.migrate
    exec uvicorn hoje.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers
fi

exec "$@"
