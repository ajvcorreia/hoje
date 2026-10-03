#!/usr/bin/env bash
# Smoke test of a FRESH Hoje stack. Needs only python3 (3.11+) on the machine running it.
#   deploy/smoke-test.sh BASE_URL MAILPIT_URL [ORIGIN]
# It registers the first account and trips the per-IP login lock, so use a throwaway stack
# (see deploy/smoke.sh). ORIGIN defaults to BASE_URL and must equal the stack's HOJE_PUBLIC_URL.
set -euo pipefail

if [ "$#" -lt 2 ]; then
  sed -n '2,5p' "$0" >&2
  exit 2
fi
exec python3 "$(dirname "$0")/smoke_test.py" "$@"
