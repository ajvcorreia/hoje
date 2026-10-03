#!/bin/sh
# Nightly PostgreSQL backups for Hoje. Runs inside postgres:17-alpine (BusyBox sh).
#
#   backup.sh          loop forever: sleep until BACKUP_SCHEDULE_HOUR (local TZ), back up, prune
#   backup.sh now      one immediate backup, then exit (non-zero on failure)
#   backup.sh health   container healthcheck: last success younger than 26 h
#                      (or the container started less than 26 h ago)
#
# Connection: standard libpq variables PGHOST, PGUSER, PGDATABASE, PGPASSWORD.
# Settings:   BACKUP_DIR (/backups), BACKUP_KEEP_DAYS (14), BACKUP_SCHEDULE_HOUR (2, 0-23).
set -eu
umask 077

BACKUP_DIR="${BACKUP_DIR:-/backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
HOUR="${BACKUP_SCHEDULE_HOUR:-2}"
MARKER="$BACKUP_DIR/.last-success"
STARTED=/tmp/backup-started
MAX_AGE_MIN=1560 # 26 h
RETRY_SECONDS=3600

log() { printf '%s backup: %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$*"; }

case "$KEEP_DAYS" in '' | *[!0-9]*) log "BACKUP_KEEP_DAYS must be a number"; exit 2 ;; esac
case "$HOUR" in '' | *[!0-9]*) log "BACKUP_SCHEDULE_HOUR must be 0-23"; exit 2 ;; esac
HOUR=$(expr "$HOUR" + 0)
if [ "$HOUR" -gt 23 ]; then log "BACKUP_SCHEDULE_HOUR must be 0-23"; exit 2; fi

run_backup() {
  stamp=$(date +%Y%m%d-%H%M%S)
  final="$BACKUP_DIR/hoje-$stamp.dump"
  tmp="$final.tmp"
  log "dumping to $final"
  if ! pg_dump --format=custom --no-owner --file="$tmp"; then
    rm -f "$tmp"
    log "FAILED: pg_dump"
    return 1
  fi
  if [ ! -s "$tmp" ] || ! pg_restore --list "$tmp" >/dev/null; then
    rm -f "$tmp"
    log "FAILED: dump is empty or unreadable"
    return 1
  fi
  mv "$tmp" "$final"
  touch "$MARKER"
  log "ok: $(wc -c <"$final") bytes"
  # Only prune after a verified new dump exists, so retention can never leave zero backups.
  find "$BACKUP_DIR" -maxdepth 1 -name 'hoje-*.dump' -mtime "+$KEEP_DAYS" -print -delete \
    | while read -r f; do log "pruned $f"; done
  find "$BACKUP_DIR" -maxdepth 1 -name 'hoje-*.dump.tmp' -mmin +60 -delete
  return 0
}

seconds_until_hour() {
  h=$(date +%H | sed 's/^0//')
  m=$(date +%M | sed 's/^0//')
  s=$(date +%S | sed 's/^0//')
  cur=$((${h:-0} * 3600 + ${m:-0} * 60 + ${s:-0}))
  delta=$((HOUR * 3600 - cur))
  [ "$delta" -le 0 ] && delta=$((delta + 86400))
  echo "$delta"
}

nap() { # interruptible sleep so SIGTERM stops the container promptly
  sleep "$1" &
  wait $!
}

case "${1:-loop}" in
  now)
    run_backup
    ;;
  health)
    if [ -f "$MARKER" ] && [ -n "$(find "$MARKER" -mmin "-$MAX_AGE_MIN")" ]; then exit 0; fi
    # No recent success: healthy only while the container is younger than 26 h.
    [ -f "$STARTED" ] && [ -n "$(find "$STARTED" -mmin "-$MAX_AGE_MIN")" ]
    ;;
  loop)
    trap 'log "stopping"; exit 0' TERM INT
    touch "$STARTED"
    mkdir -p "$BACKUP_DIR"
    log "scheduled daily at ${HOUR}:00 ($(date +%Z)); keeping $KEEP_DAYS days"
    while :; do
      wait_s=$(seconds_until_hour)
      log "next backup in ${wait_s}s"
      nap "$wait_s"
      until run_backup; do
        log "retrying in ${RETRY_SECONDS}s"
        nap "$RETRY_SECONDS"
      done
    done
    ;;
  *)
    echo "usage: backup.sh [loop|now|health]" >&2
    exit 2
    ;;
esac
