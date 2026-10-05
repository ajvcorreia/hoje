# Backup and restore

The `worker` service backs up the database itself. Every night at `BACKUP_SCHEDULE_HOUR` (local
time in `TZ`) it runs `pg_dump -Fc`, verifies the dump with `pg_restore --list`, and writes it
to `/backups/hoje-YYYYmmdd-HHMMSS.dump` inside the worker container. Dumps older than
`BACKUP_KEEP_DAYS` (default 14) are deleted, but only after a new dump has been verified, and
the newest dump is never deleted. A dump only gets its final name once it is complete.

There is no separate backup container any more. The backups volume is mounted into the
**worker only**: the API container cannot see the dump files. It is the Docker named volume
`hoje_backups`, or the host directory in `HOJE_BACKUP_DIR_HOST` if you set one (that directory
must be writable by uid 10001: `sudo chown 10001:10001 /srv/hoje/backups`).

The instance owner (the first account that was created) sees the schedule, the last backup and
the recent runs in **Settings > Backups**, and can start one with **Back up now**. Failed backups
show up there and in the worker log (`docker compose logs worker`); the worker container stays
healthy when a backup fails.

There is deliberately **no download button and no restore button** in the app. Restoring is a
command-line operation on the server, and a download endpoint would let anyone who steals a
session cookie copy your whole database.

All commands below run on the production host from the repository root. Define a shortcut first:

```bash
DC="docker compose -f deploy/compose.prod.yml --env-file deploy/.env"
```

Add `-f deploy/compose.prod.proxy-network.yml` to `DC` if you deploy with that overlay.

## Take a backup now

Use **Settings > Backups > Back up now**, or wait for the nightly run. To see what exists:

```bash
$DC exec worker ls -l /backups
$DC logs --tail 20 worker | grep backup
```

Settings shows a warning when the last successful backup is older than 26 hours. A missed
schedule (for example the stack was stopped at 02:00) is made up for when the worker starts, if
the last backup is more than 24 hours old.

## Restore

Restoring replaces all data in the `hoje` database with the contents of the dump. Everything
written after the dump was taken is lost, so take a fresh backup first if the database is still
readable (see above).

1. Pick the dump and copy it out of the worker's volume (this also works while the worker is
   stopped):

   ```bash
   $DC exec worker ls -l /backups
   $DC cp worker:/backups/hoje-20260101-020000.dump ./
   ```

   (Or use a dump you already copied off the host.)

2. Stop everything that talks to the database. Keep `db` running.

   ```bash
   $DC stop web api worker
   ```

3. Restore it into the running database. `pg_restore --clean --if-exists` drops and recreates
   every object in the dump; `--single-transaction` makes it all-or-nothing, so a failure leaves
   the existing data untouched.

   ```bash
   $DC exec -T db pg_restore --clean --if-exists --no-owner --single-transaction \
       -U hoje --dbname hoje < hoje-20260101-020000.dump
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
$DC up -d db
$DC exec -T db pg_restore --clean --if-exists --no-owner --single-transaction \
    -U hoje --dbname hoje < /path/to/hoje-20260101-020000.dump
$DC up -d
```

Back up `deploy/.env` (at least `HOJE_SECRET_KEY` and `POSTGRES_PASSWORD`) separately from the
database dumps. Without the original `HOJE_SECRET_KEY` a restored database still works, but
stored TOTP secrets cannot be decrypted (sign in with a recovery code, then disable and
re-enrol 2FA).

**Dumps are plaintext.** Only the TOTP seeds are encrypted inside the database; everything
else (event titles and notes, your email address, password hashes, session metadata) is stored
and dumped in the clear. Anyone who obtains a dump can read all of it, with or without the key.
The worker can read, create and delete the files in its backups volume, so a compromised worker
can also destroy them. Encrypt every copy that leaves the host (for example `age` or `restic`,
see [the hardening checklist, section 7](../../docs/hardening-checklist.md)), keep encrypted
copies off the host, and keep the encryption key away from the backup storage.

## Copy backups off the host

Dumps on the same disk as the database do not protect against losing the machine. Copy them
elsewhere regularly.

From a named volume, via the worker container:

```bash
$DC exec worker ls -l /backups
$DC cp worker:/backups/hoje-20260101-020000.dump ./
scp hoje-20260101-020000.dump user@other-host:/srv/hoje-backups/
```

Or archive the whole volume in one go (works even when the stack is stopped):

```bash
docker run --rm -v hoje_backups:/backups:ro alpine tar -C /backups -cf - . > hoje-backups.tar
```

With `HOJE_BACKUP_DIR_HOST` pointing at a host directory, use any tool you like on that
directory, for example a cron job:

```bash
rsync -a --delete /srv/hoje/backups/ user@other-host:/srv/hoje-backups/
```

Dumps are created readable by the app user only (uid 10001, mode 0600); use `sudo` for host-side
copies.

## Upgrading from the separate `backup` container (before 1.1.0)

1. Delete the `backup` service from your compose file (the shipped `compose.prod.yml` no longer
   has it), and `deploy/backup/backup.sh` is gone too.
2. If you set a host path in `HOJE_BACKUP_DIR`, rename the variable to `HOJE_BACKUP_DIR_HOST`
   (`HOJE_BACKUP_DIR` now means the directory inside the worker, `/backups`).
3. Existing dumps: with the default named volume the worker mounts the same `hoje_backups`
   volume, so the old dumps are already there, but the volume belongs to root and the worker
   (uid 10001) could not write to it: backups would fail with "cannot write". Fix it once, which
   also makes the old dumps readable and
   prunable by the app user:

   ```bash
   docker run --rm -v hoje_backups:/b alpine chown -R 10001:10001 /b
   ```

   With a host directory use `sudo chown -R 10001:10001 <dir>`. Old dumps are pruned by age like
   new ones.
