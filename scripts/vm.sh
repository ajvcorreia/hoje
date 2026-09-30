#!/usr/bin/env bash
# Sync the working tree to the test VM and run verification there.
# The dev machine only writes code; all tests, builds and containers run on the VM.
#
# Env:  HOJE_VM=user@host            (required)
#       HOJE_VM_SSH_OPTS="-i ~/.ssh/key"  (optional)
#       HOJE_SLUG=name               (optional; defaults to current branch, '/' -> '-')
#
# Usage:
#   scripts/vm.sh sync                          copy tracked + untracked (non-ignored) files
#   scripts/vm.sh backend  '<cmd>'              sync, then run cmd in backend-tools (cwd backend/)
#   scripts/vm.sh frontend '<cmd>'              sync, then run cmd in frontend-tools (cwd frontend/)
#   scripts/vm.sh compose  <compose args...>    docker compose -p hoje-test in the synced dir
#   scripts/vm.sh exec     '<cmd>'              shell cmd inside the synced dir on the VM
#   scripts/vm.sh pull     <path...>            copy generated files back (lockfiles, openapi.json)
set -euo pipefail

: "${HOJE_VM:?set HOJE_VM=user@host}"
REPO=$(git rev-parse --show-toplevel)
SLUG=${HOJE_SLUG:-$(git -C "$REPO" rev-parse --abbrev-ref HEAD | tr '/' '-')}
REMOTE_ROOT='~/hoje-test'
REMOTE_SRC="$REMOTE_ROOT/src/$SLUG"
# shellcheck disable=SC2086
vm() { ssh -o BatchMode=yes ${HOJE_VM_SSH_OPTS:-} "$HOJE_VM" "$@"; }

sync() {
  cd "$REPO"
  git ls-files -co --exclude-standard | while IFS= read -r f; do [ -e "$f" ] && printf '%s\n' "$f"; done \
    | tar -czf - -T - \
    | vm "set -e; mkdir -p $REMOTE_SRC $REMOTE_ROOT/cache/uv $REMOTE_ROOT/cache/npm; cd $REMOTE_SRC;
          find . -mindepth 1 \( -path ./frontend/node_modules -o -path ./backend/.venv \) -prune -o -type f -print0 | xargs -0 -r rm -f;
          tar -xzf -"
  echo "synced -> $HOJE_VM:$REMOTE_SRC" >&2
}

tools() { # service cmd
  local q; q=$(printf '%q' "$2")
  vm "cd $REMOTE_SRC && HOJE_SRC=\$PWD HOJE_ROOT=\$(cd $REMOTE_ROOT && pwd) \
      docker compose -p hoje-test -f deploy/compose.tools.yml --profile tools run --rm -T $1 bash -lc $q"
}

cmd=${1:-}; shift || true
case "$cmd" in
  sync) sync ;;
  backend) sync; tools backend-tools "$1" ;;
  frontend) sync; tools frontend-tools "$1" ;;
  compose) sync; vm "cd $REMOTE_SRC && docker compose -p hoje-test $(printf '%q ' "$@")" ;;
  exec) sync; vm "cd $REMOTE_SRC && bash -lc $(printf '%q' "$1")" ;;
  pull) vm "cd $REMOTE_SRC && tar -czf - $(printf '%q ' "$@")" | tar -xzf - -C "$REPO"; echo "pulled: $*" >&2 ;;
  *) sed -n '2,20p' "$0"; exit 1 ;;
esac
