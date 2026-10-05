#!/usr/bin/env bash
# Run deploy/smoke_test.py against a throwaway stack built from deploy/compose.e2e.yml
# (services e2e-db, e2e-api, e2e-worker, e2e-web, e2e-mailpit; worker polls every 2 s).
# The test client runs in a python:3.13-alpine container on the stack's own networks.
# smoke_test.py has the owner press "Back up now" (POST /api/v1/backups) and waits for the run to
# succeed. After a green run this script copies the newest dump out of e2e-worker (/backups)
# and restores it into a second throwaway PostgreSQL to compare row counts.
#
# Safety: the compose project name is shared with the LAN test stack, so teardown removes only
# the e2e services by explicit name. Never `down --remove-orphans` / `down -v` here.
#
# Env: HOJE_API_IMAGE / HOJE_WEB_IMAGE  image tags (default hoje-test/{api,web}:e2e)
#      SMOKE_SKIP_BUILD=1               use the images as they are (they must already exist)
#      SMOKE_PYTHON_IMAGE               client image (default python:3.13-alpine)
set -uo pipefail

cd "$(dirname "$0")/.."
export HOJE_API_IMAGE="${HOJE_API_IMAGE:-hoje-test/api:e2e}"
export HOJE_WEB_IMAGE="${HOJE_WEB_IMAGE:-hoje-test/web:e2e}"
PYTHON_IMAGE="${SMOKE_PYTHON_IMAGE:-python:3.13-alpine}"
PG_IMAGE="postgres:17-alpine"
# Must equal HOJE_PUBLIC_URL in compose.e2e.yml (the API checks the Origin header against it).
ORIGIN="http://e2e-web:8080"
NET_INTERNAL="hoje-test_e2e_internal"
NET_EDGE="hoje-test_e2e_edge"
DUMP_DIR=

SERVICES=(e2e-db e2e-api e2e-worker e2e-web e2e-mailpit)
dc() { docker compose -p hoje-test -f deploy/compose.e2e.yml "$@"; }

teardown() {
  docker rm -f hoje-test-smoke-client hoje-test-smoke-restore >/dev/null 2>&1
  [ -n "${DUMP_DIR:-}" ] && rm -rf -- "$DUMP_DIR"
  dc rm -sfv "${SERVICES[@]}" >/dev/null 2>&1 || true
  docker network rm "$NET_INTERNAL" "$NET_EDGE" >/dev/null 2>&1 || true
}
trap teardown EXIT

teardown # clean slate in case a previous run was killed
DUMP_DIR=$(mktemp -d)

if [ "${SMOKE_SKIP_BUILD:-}" != "1" ]; then
  dc build e2e-api e2e-web || exit 1
fi

dc up -d --wait "${SERVICES[@]}" || {
  dc logs --tail 80 e2e-api e2e-web e2e-worker || true
  exit 1
}

# The client needs both networks: e2e-web is on e2e_edge, e2e-mailpit on e2e_internal.
# `docker run` takes one network, so create, connect the second, then start attached.
docker create --name hoje-test-smoke-client \
  --network "$NET_EDGE" \
  --security-opt no-new-privileges:true --cap-drop ALL --read-only --tmpfs /tmp \
  --memory 128m -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
  -v "$PWD/deploy/smoke_test.py:/smoke/smoke_test.py:ro" \
  --entrypoint python "$PYTHON_IMAGE" \
  /smoke/smoke_test.py http://e2e-web:8080 http://e2e-mailpit:8025 "$ORIGIN" >/dev/null || exit 1
docker network connect "$NET_INTERNAL" hoje-test-smoke-client || exit 1
docker start -a hoje-test-smoke-client
code=$?
docker rm -f hoje-test-smoke-client >/dev/null 2>&1

if [ "$code" -ne 0 ]; then
  echo "smoke test failed (exit $code); recent API log:" >&2
  dc logs --tail 40 e2e-api e2e-worker >&2 || true
  exit "$code"
fi

# --- backup and restore round trip on the (now populated) throwaway database -----------------
# smoke_test.py already asked the owner's "Back up now" and waited for the run to succeed, so
# the worker's /backups holds a verified dump. Take the newest one out of e2e-worker and
# restore it into a fresh PostgreSQL.
count() { # container table
  docker exec "$1" psql -U hoje -d hoje -Atc "select count(*) from $2" 2>/dev/null
}

echo "--- backup: newest dump in the e2e-worker /backups volume"
dump_name=$(dc exec -T e2e-worker sh -c 'ls -t /backups/hoje-*.dump 2>/dev/null | head -1') \
  || { echo "FAIL could not list /backups in e2e-worker" >&2; exit 1; }
dump_name=$(printf '%s' "$dump_name" | tr -d '\r')
[ -n "$dump_name" ] || { echo "FAIL no dump in e2e-worker:/backups" >&2; exit 1; }
dc exec -T e2e-worker cat "$dump_name" >"$DUMP_DIR/smoke.dump" \
  || { echo "FAIL could not read $dump_name" >&2; exit 1; }
dump_bytes=$(wc -c <"$DUMP_DIR/smoke.dump")
[ "$dump_bytes" -gt 0 ] || { echo "FAIL empty dump $dump_name" >&2; exit 1; }
echo "PASS backup: $dump_name ($dump_bytes bytes) copied out of e2e-worker"

echo "--- restore: pg_restore into a fresh throwaway PostgreSQL"
docker run -d --name hoje-test-smoke-restore --network "$NET_INTERNAL" \
  -e POSTGRES_USER=hoje -e POSTGRES_DB=hoje -e POSTGRES_PASSWORD=restore-password \
  --tmpfs /var/lib/postgresql/data "$PG_IMAGE" >/dev/null || exit 1
for _ in $(seq 1 60); do
  [ "$(docker exec hoje-test-smoke-restore psql -U hoje -d hoje -Atc 'select 1' 2>/dev/null)" = 1 ] && break
  sleep 1
done
docker exec -i hoje-test-smoke-restore \
  pg_restore -U hoje -d hoje --clean --if-exists --no-owner --single-transaction \
  <"$DUMP_DIR/smoke.dump" || { echo "FAIL restore" >&2; exit 1; }

status=0
for table in users categories events reminders sessions; do
  src=$(count "$(dc ps -q e2e-db)" "$table")
  dst=$(count hoje-test-smoke-restore "$table")
  if [ -n "$src" ] && [ "$src" = "$dst" ]; then
    echo "PASS backup/restore: $table rows $src = $dst"
  else
    echo "FAIL backup/restore: $table rows source=$src restored=$dst" >&2
    status=1
  fi
done
[ "$(count hoje-test-smoke-restore users)" -ge 1 ] 2>/dev/null || { echo "FAIL restored users table is empty" >&2; status=1; }
rows=$(docker exec hoje-test-smoke-restore psql -U hoje -d hoje -Atc "select count(*) from backup_runs where status = 'succeeded'" 2>/dev/null)
if [ "${rows:-0}" -ge 1 ] 2>/dev/null; then
  echo "PASS backup/restore: backup_runs holds $rows succeeded run(s)"
else
  echo "FAIL backup/restore: no succeeded backup_runs row in the restored database" >&2
  status=1
fi
exit "$status"
