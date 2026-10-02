#!/usr/bin/env bash
# Run the Playwright suite against a throwaway stack (deploy/compose.e2e.yml).
#
# Safety: the compose project name is shared with the LAN test stack, so teardown removes
# only the e2e services by explicit name. Never `down --remove-orphans` / `down -v` here.
#
# Env: HOJE_API_IMAGE / HOJE_WEB_IMAGE  image tags (default hoje-test/{api,web}:e2e)
#      E2E_SKIP_BUILD=1                 use the images as they are (CI loads them beforehand)
#      E2E_ARTIFACTS_DIR                where failure reports are copied (default ./e2e-artifacts)
#      E2E_PLAYWRIGHT_ARGS              extra args for `playwright test`
set -uo pipefail

cd "$(dirname "$0")/.."
export HOJE_API_IMAGE="${HOJE_API_IMAGE:-hoje-test/api:e2e}"
export HOJE_WEB_IMAGE="${HOJE_WEB_IMAGE:-hoje-test/web:e2e}"
HOJE_UID="$(id -u)"
HOJE_GID="$(id -g)"
export HOJE_UID HOJE_GID

SERVICES=(e2e-db e2e-api e2e-worker e2e-web e2e-mailpit playwright)
dc() { docker compose -p hoje-test -f deploy/compose.e2e.yml --profile e2e "$@"; }

teardown() {
  dc rm -sfv "${SERVICES[@]}" >/dev/null 2>&1 || true
  # Compose leaves the (empty) networks behind; remove just ours.
  docker network rm hoje-test_e2e_internal hoje-test_e2e_edge >/dev/null 2>&1 || true
}
trap teardown EXIT

teardown # clean slate in case a previous run was killed
rm -rf frontend/playwright-report frontend/test-results

if [ "${E2E_SKIP_BUILD:-}" != "1" ]; then
  dc build e2e-api e2e-web || exit 1
fi

dc up -d --wait e2e-db e2e-mailpit e2e-api e2e-worker e2e-web || {
  dc logs --tail 80 e2e-api e2e-web e2e-worker || true
  exit 1
}

if [ -n "${E2E_PLAYWRIGHT_ARGS:-}" ]; then
  # shellcheck disable=SC2086
  dc run --rm -T playwright sh -c "npm ci --no-audit --no-fund && npx playwright test ${E2E_PLAYWRIGHT_ARGS}"
else
  dc run --rm -T playwright
fi
code=$?

if [ "$code" -ne 0 ]; then
  dest="${E2E_ARTIFACTS_DIR:-e2e-artifacts}"
  mkdir -p "$dest"
  cp -r frontend/playwright-report frontend/test-results "$dest"/ 2>/dev/null || true
  dc logs --tail 60 e2e-api >"$dest/api.log" 2>&1 || true
  echo "e2e failed (exit $code); reports copied to $dest" >&2
fi
exit "$code"
