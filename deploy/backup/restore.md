# Backup and restore

The `backup` service in `deploy/compose.prod.yml` writes a PostgreSQL custom-format dump
(`pg_dump -Fc`) to `/backups/hoje-YYYYmmdd-HHMMSS.dump` every night at `BACKUP_SCHEDULE_HOUR`
(local `TZ`), verifies it with `pg_restore --list`, and deletes dumps older than
`BACKUP_KEEP_DAYS` (default 14). A dump is only written under its final name once it is complete.

The backups volume is the Docker named volume `hoje_backups`, or the host directory in
`HOJE_BACKUP_DIR` if you set one.

All commands below run on the production host from the repository root. Define a shortcut first:

```bash
DC="docker compose -f deploy/compose.prod.yml --env-file deploy/.env"
```

Add `-f deploy/compose.prod.proxy-network.yml` to `DC` if you deploy with that overlay.

## Take a backup now

```bash
$DC exec backup sh /backup/backup.sh now
$DC exec backup ls -lh /backups
$DC logs --tail 20 backup
```

`docker compose ps` shows the backup container as `unhealthy` if there has been no successful
backup for 26 hours (it is healthy during the first 26 hours after it starts).

## Restore

Restoring replaces all data in the `hoje` database with the contents of the dump. Everything
written after the dump was taken is lost, so take a fresh backup first if the database is still
readable (see above).

1. Stop everything that talks to the database. Keep `db` (and `backup`) running.

   ```bash
   $DC stop web api worker
   ```

2. Pick the dump:

   ```bash
   $DC exec backup ls -lh /backups
   ```

3. Restore it into the running database. `pg_restore --clean --if-exists` drops and recreates
   every object in the dump; `--single-transaction` makes it all-or-nothing, so a failure leaves
   the existing data untouched. The `backup` container already has the connection settings.

   ```bash
   $DC exec backup pg_restore --clean --if-exists --no-owner --single-transaction \
       --dbname hoje /backups/hoje-20260101-020000.dump
   ```

   To restore a dump that is not in the backups volume (for example one you copied back from
   elsewhere), stream it in instead of naming a file:

   ```bash
   $DC exec -T backup pg_restore --clean --if-exists --no-owner --single-transaction \
       --dbname hoje < /path/to/hoje-20260101-020000.dump
   ```

4. Start the application again. The API applies any migrations newer than the dump on start.

   ```bash
   $DC up -d
   $DC ps
   ```

5. Check that you can sign in and that your events are there.

### Restoring onto a brand-new host

Install Docker, copy `deploy/.env` (it holds `HOJE_SECRET_KEY`, which must be the original: the
dump stores TOTP secrets encrypted with it), then:

```bash
$DC pull
$DC up -d db backup
$DC exec -T backup pg_restore --clean --if-exists --no-owner --single-transaction \
    --dbname hoje < /path/to/hoje-20260101-020000.dump
$DC up -d
```

Back up `deploy/.env` (at least `HOJE_SECRET_KEY` and `POSTGRES_PASSWORD`) separately from the
database dumps; a dump alone cannot be used without the key.

## Copy backups off the host

Dumps on the same disk as the database do not protect against losing the machine. Copy them
elsewhere regularly.

From a named volume, via the running `backup` container:

```bash
$DC cp backup:/backups/hoje-20260101-020000.dump ./
scp hoje-20260101-020000.dump user@other-host:/srv/hoje-backups/
```

Or archive the whole volume in one go (works even when the stack is stopped):

```bash
docker run --rm -v hoje_backups:/backups:ro alpine tar -C /backups -cf - . > hoje-backups.tar
```

With `HOJE_BACKUP_DIR` pointing at a host directory, use any tool you like on that directory,
for example a cron job:

```bash
rsync -a --delete /srv/hoje/backups/ user@other-host:/srv/hoje-backups/
```

Dumps are created readable by root only (mode 0600); use `sudo` for host-side copies.
