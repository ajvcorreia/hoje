# Hoje

A self-hosted personal planner replacing a spreadsheet, with a desktop month-column grid and mobile day view. Track vacation balance, view Portugal and UAE holidays, receive email reminders, enable two-factor authentication, and sync changes live across devices.

## Features

- **Desktop month grid**: 12 months side by side, weekday-aligned rows, weekends shaded, week numbers, today highlighted.
- **Mobile calendar**: day and week-strip views with quick add (click-type-Enter).
- **Multiple views**: Year overview and Agenda view for flexible planning.
- **Multi-day events**: visual blocks spanning columns, per-event vertical names, same-day halves with "+N" indicator.
- **Categories with colours**: 12-colour palette, filter chips, customizable icons.
- **Vacation balance**: working-day counting, carry-over policy, leave impact preview on events.
- **Holiday overlays**: Portugal and UAE holiday calendars (bundled data, user-selectable).
- **Email reminders**: due-time scheduling with configurable offsets, retry logic, delivery notifications.
- **Live sync across devices**: Server-Sent Events with Postgres LISTEN/NOTIFY, real-time change warnings.
- **Two-factor authentication**: TOTP-based 2FA with single-use recovery codes and encrypted storage.
- **Security**: Argon2id password hashing, CSRF protection, progressive brute-force lockouts, trusted-device relief.
- **Themes and accessibility**: light/dark mode, configurable text size, inclusive colour palette.
- **Installable PWA**: works offline, installable on mobile and desktop.
- **Search**: find events by title (case-insensitive, indexed), filter by category.

## Documentation

- **[PLAN.md](docs/PLAN.md)**: Architecture decisions, database schema, API contract, and implementation conventions.
- **[Threat Model](docs/threat-model.md)**: Security assumptions and attack surface for self-hosted deployments.
- **[Hardening Checklist](docs/hardening-checklist.md)**: Pre-deployment security configuration steps.
- **[Backup and Restore](deploy/backup/restore.md)**: Backup scheduling, verification, and recovery procedures.
- **[CHANGELOG.md](CHANGELOG.md)**: Version history and notable changes.

## Architecture

Hoje is built with a modern stack designed for reliability and simplicity:

- **Backend**: FastAPI + SQLAlchemy async + PostgreSQL + Alembic migrations
- **Frontend**: React 19 + TypeScript + Tailwind CSS + TanStack Query
- **Realtime**: Server-Sent Events with Postgres LISTEN/NOTIFY
- **Deployment**: Docker + Caddy reverse proxy
- **Infrastructure**: Self-hosted on a single server; no Redis, no microservices

See [docs/PLAN.md](docs/PLAN.md) for architectural decisions, database contracts, and API specs.

## Quick start

Everything runs in containers; you only need Docker with Compose v2.

**Development stack** (hot reload for API and frontend, Mailpit for email):

```bash
docker compose -f deploy/compose.dev.yml up --build
```

| Service | URL |
|---|---|
| Frontend (Vite) | http://localhost:5173 |
| API + Swagger UI | http://localhost:8000/api/docs |
| Mailpit | http://localhost:8025 |

**Test stack** (production-like images, plain HTTP on a LAN port, throwaway database):

```bash
cp deploy/test.env.example deploy/.env.test   # then edit; the file must exist for --env-file
docker compose -p hoje-test --env-file deploy/.env.test -f deploy/compose.test.yml up -d --build --wait
```

The app is then on port `8190` and Mailpit on `8191`. Stop and wipe it with
`docker compose -p hoje-test -f deploy/compose.test.yml down -v`.

**Regenerating contracts** after changing API schemas: run `uv run python -m hoje.openapi` in
`backend/`, then `npm run gen:api` in `frontend/`. CI fails if either file is stale.

## Environment variables

Configuration is managed through environment variables. Copy `.env.example` to `.env` and customize for your installation. Key settings include the database URL, SMTP configuration for email reminders, and the TOTP encryption key. For details, see [.env.example](.env.example).

## Testing on the test VM

Use `scripts/vm.sh` to run tests on an isolated VM. The script handles backend (Python/uv) and frontend (Node/npm) verification without requiring a local runtime:

```bash
bash scripts/vm.sh backend 'uv sync && uv run ruff check . && uv run pytest -q'
bash scripts/vm.sh frontend 'npm ci && npm run lint && npm run typecheck && npm test'
bash scripts/vm.sh pull backend/uv.lock  # Bring generated files back to commit
```

See [docs/PLAN.md](docs/PLAN.md) §7 for details.

## CI/CD and GitHub secrets

Two workflows live in `.github/workflows/`:

- **`ci.yml`** runs on every pull request and every push to `main`: backend lint, format and
  tests against PostgreSQL, OpenAPI and migration drift checks, frontend lint, typecheck, tests and
  build, API client drift check, Docker builds with a Trivy scan (HIGH/CRITICAL, unfixed ignored),
  `pip-audit` / `npm audit`, and the Playwright end-to-end suite. It needs no secrets.
- **`release.yml`** runs on pushes to `main` and on tags `vX.Y.Z` (never on pull requests). For
  each of the two images it builds, scans with Trivy (a finding fails the release before anything is
  pushed), and pushes to Docker Hub for `linux/amd64`.

| Image | Built from | Tags |
|---|---|---|
| `NAMESPACE/hoje-api` (API and worker) | `backend/` | `latest` (main only), `sha-<short>`, and for a tag `vX.Y.Z`: `X.Y.Z` and `X.Y` |
| `NAMESPACE/hoje-web` (Caddy and SPA) | repo root, `deploy/web.Dockerfile` | same |

Images carry OCI labels for source, revision and version.

### One-time setup

Until these exist the release workflow is skipped (no failed runs on `main`). Nothing in this
repository touches Docker Hub until you do the following.

1. On Docker Hub, check that the names `NAMESPACE/hoje-api` and `NAMESPACE/hoje-web` are free (or
   already yours) before the first push; pushing creates the repositories.
2. Create an access token: Docker Hub, Account settings, Personal access tokens, scope
   **Read & Write**. Copy it once; it is shown a single time.
3. In the GitHub repository, Settings, Secrets and variables, Actions:
   - **Secrets** tab, new repository secrets: `DOCKERHUB_USERNAME` (your Docker Hub user name) and
     `DOCKERHUB_TOKEN` (the access token).
   - **Variables** tab, new repository variable: `DOCKERHUB_NAMESPACE` (the user or organisation
     that owns the images; usually the same as the user name, lower case).
4. Push to `main`, or release a version:

   ```bash
   git tag v0.1.0 && git push origin v0.1.0
   ```

If the variable is set but a secret is missing, the job logs a warning and skips the push.

## Deployment: test VM

The LAN test stack (`deploy/compose.test.yml`) builds the images on the VM and serves plain HTTP:
the app on port `8190`, Mailpit (catches all outgoing mail) on `8191`.

```bash
cp deploy/test.env.example deploy/.env.test    # edit; the file must exist for --env-file
docker compose -p hoje-test --env-file deploy/.env.test -f deploy/compose.test.yml up -d --build --wait
```

`scripts/vm.sh` syncs the working tree to the VM and runs checks there (see
[Testing on the test VM](#testing-on-the-test-vm)):

```bash
bash scripts/vm.sh exec 'bash deploy/e2e.sh'      # Playwright suite on a throwaway stack
bash scripts/vm.sh exec 'bash deploy/smoke.sh'    # smoke test on a throwaway stack
```

Both bring up their own stack from `deploy/compose.e2e.yml` (services `e2e-*`, tmpfs database, no
volumes) and tear down only those services by name. They never touch the LAN test stack that lives
in the same Compose project, so never run `down -v` or `--remove-orphans` against that project.

`deploy/smoke.sh` runs `deploy/smoke_test.py` from a `python:3.13-alpine` container on the e2e
networks. It checks `/healthz` and `/readyz`, registers the first user, signs in, enables 2FA and
completes an MFA login, creates events, verifies that the live-sync (SSE) frame arrives within 5 s,
waits for the reminder email in Mailpit, checks the security headers and that forged
`X-Forwarded-For` / `X-Real-IP` headers cannot dodge the per-IP login lock. You can point the same
script at any fresh stack: `deploy/smoke-test.sh BASE_URL MAILPIT_URL [ORIGIN]` (it registers the
first account, so never use it on a stack with real data).

## Deployment: production behind Nginx Proxy Manager

Production runs the published images (`deploy/compose.prod.yml`): PostgreSQL 17, `api`, `worker`,
`web` (Caddy serving the SPA and proxying `/api`). The `worker` also runs the nightly database backup
(`pg_dump` ships in the API image). TLS is terminated
by your existing **Nginx Proxy Manager (NPM)**, which proxies to `hoje-web` over plain HTTP.

### Prerequisites

- A Linux host with Docker Engine and Compose v2, outbound access to Docker Hub and your SMTP
  server.
- NPM running on the same host (or reachable from it), and a DNS name pointing at NPM.
- The images pushed by `release.yml` (see CI/CD above).

### 1. Configure

```bash
cp deploy/prod.env.example deploy/.env      # gitignored; edit every value
```

Generate secrets with `openssl rand -base64 32` (`HOJE_SECRET_KEY`) and `openssl rand -hex 24`
(`POSTGRES_PASSWORD`). Set `DOCKERHUB_NAMESPACE`, the SMTP settings and `HOJE_TAG`: pin a release
version such as `1.0.0` rather than `latest`, so that an image pushed to the tag cannot change what
you run without you noticing; upgrade by editing the tag (see Upgrades). Also set:

- `HOJE_PUBLIC_URL`: the **https** URL users type (`https://hoje.example.com`). Cookies are
  `Secure` and the Origin check compares against it, so a wrong value breaks sign-in.
- `TRUSTED_PROXIES`: **required** (compose refuses to start without it): the IP or CIDR NPM
  connects from, as seen by `hoje-web` (see below and the comments in `deploy/prod.env.example`).
- `TZ` and `BACKUP_SCHEDULE_HOUR` for the backup time; optionally `BACKUP_KEEP_DAYS` and
  `HOJE_BACKUP_DIR_HOST` (see Backup and restore).

Back up `deploy/.env`, in particular `HOJE_SECRET_KEY`: the database holds TOTP secrets encrypted
with it.

### 2. Choose how NPM reaches hoje-web

| NPM runs | Set | NPM forwards to |
|---|---|---|
| **in a container on this host** (recommended) | `HOJE_PROXY_NETWORK=<NPM network name>`, add `-f deploy/compose.prod.proxy-network.yml` to every compose command | `hoje-web`, port `8080` |
| natively or with host networking on this host | `HOJE_BIND=127.0.0.1` (default) | `127.0.0.1`, port `HOJE_HTTP_PORT` |
| on another machine | `HOJE_BIND=<this host LAN IP>` and firewall the port to NPM only | that IP, port `HOJE_HTTP_PORT` |

`docker network ls` lists network names; `docker network inspect <name>` shows the subnet. Put
NPM's address (or its network's subnet) in `TRUSTED_PROXIES`. Caddy believes `X-Forwarded-For` only
from those addresses and hands the API the resulting client address in `X-Real-IP`; the login
throttle keys on it. A wrong or too-wide value either collapses every visitor into NPM's single IP
or lets a client choose its own IP, so set it precisely. The API itself is never published and sits
only on internal networks plus the one it shares with `hoje-web`: nothing else may be able to reach
it, because it trusts `X-Real-IP` (`HOJE_TRUST_REAL_IP_HEADER`).

### 3. Start it

```bash
DC="docker compose -f deploy/compose.prod.yml --env-file deploy/.env"   # add the -f overlay if used
$DC pull
$DC up -d
$DC ps      # everything healthy; migrations ran when the API started
```

### 4. Nginx Proxy Manager proxy host

Hosts, Proxy Hosts, Add Proxy Host:

- **Details**: domain name = your domain; scheme `http`; forward host/IP and port from step 2;
  turn **Block Common Exploits** on. Websockets support is not needed (live sync uses
  Server-Sent Events, which are plain HTTP).
- **SSL**: request a new Let's Encrypt certificate; turn on **Force SSL**, **HTTP/2 Support** and
  **HSTS Enabled**.
- **Advanced**, custom Nginx configuration, exactly:

  ```
  proxy_buffering off;
  proxy_cache off;
  proxy_read_timeout 1h;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  client_max_body_size 1m;
  ```

  Live sync across devices streams events over one long-lived response: without
  `proxy_buffering off` Nginx holds the events back, and the default 60 s `proxy_read_timeout`
  would cut the stream (the app reconnects, but updates would lag). The `X-Forwarded-For` line
  makes NPM pass the real client address on, which `hoje-web` resolves against `TRUSTED_PROXIES`.
  `client_max_body_size 1m` rejects oversized request bodies at the edge (NPM's default is far
  larger); Caddy and the API enforce the same cap behind it.

Check `https://<your domain>/healthz`, sign in, and make a change in two browsers to see it appear
live.

### 5. Create your account first

**Register before anyone else can find the site**: registration is open until the first user
exists. The browser must use the https URL (the Origin check and `Secure` cookies do not work over
plain HTTP), so do this right after step 4. To be safe, attach an NPM Access List that allows only
your own IP to the proxy host until the account exists. Better still, set `HOJE_SETUP_TOKEN` in
`deploy/.env` (generate it with `openssl rand -base64 24`): the Create-account form then asks for
it, and wrong guesses are rate limited per address. The API logs a warning at start-up when
production has no users and no token. The token is ignored once the first account exists, so you can
remove it afterwards. Then enable 2FA under Settings and, if you
used an Access List, remove it.

## Backup and restore

The `worker` dumps the database nightly at `BACKUP_SCHEDULE_HOUR` (local `TZ`) with
`pg_dump -Fc`, verifies the dump, and keeps `BACKUP_KEEP_DAYS` days (default 14) in the `/backups`
volume that only the worker mounts: the named volume `hoje_backups`, or the host directory in
`HOJE_BACKUP_DIR_HOST` (which must be writable by uid 10001: `sudo chown 10001:10001 <dir>`).
Set `HOJE_BACKUP_ENABLED=false` to turn backups off.

The instance owner (the first account) sees the last backup, the schedule and recent runs in
**Settings > Backups** (a warning appears when the last backup is older than 26 hours) and can
start one with **Back up now**. A failed backup is shown there and logged; it does not make the
worker container unhealthy. There is deliberately no download or restore button: restores are
done from the server command line, and a download endpoint would let a stolen session copy the
whole database.

```bash
$DC exec worker ls -l /backups                       # the dumps
$DC cp worker:/backups/hoje-20260101-020000.dump .   # copy one off the host
```

Dumps are **plaintext** and the worker can delete them: keep encrypted copies on another machine.
Restore steps (stop `web`/`api`/`worker`, `pg_restore --clean --if-exists`, start) and how to copy
dumps off the host are in [deploy/backup/restore.md](deploy/backup/restore.md). Keep copies on
another machine: a dump on the same disk does not survive losing the host.

## Upgrades

1. Take a backup (Settings > Backups > Back up now) and wait for it to succeed.
2. Set `HOJE_TAG` in `deploy/.env` to the new version (for example `0.2.0`; `latest` follows
   `main`), then:

   ```bash
   $DC pull
   $DC up -d
   $DC ps
   ```

   Database migrations run automatically when the API container starts (under an advisory lock),
   and the worker waits for a healthy API.
3. **Roll back**: set `HOJE_TAG` to the previous version and `$DC up -d`. If the new version applied
   a migration, the old code may not run against the new schema: stop `web api worker` and restore
   the backup from step 1 as described in [restore.md](deploy/backup/restore.md) before starting
   the old tag.

**Upgrading to 1.1.0 from an earlier version:** the separate `backup` container is gone. Delete the
`backup` service from your compose file (or take the new `deploy/compose.prod.yml`), rename
`HOJE_BACKUP_DIR` to `HOJE_BACKUP_DIR_HOST` if you used a host path, and give the old dumps to the
new owner once: `docker run --rm -v hoje_backups:/b alpine chown -R 10001:10001 /b` (see
[restore.md](deploy/backup/restore.md)). The new worker takes a first backup when it starts (it has no
record of an earlier one); check Settings > Backups to confirm it succeeded.

## Security

Hoje is meant for one owner, but it is internet-facing, so the design assumes hostile traffic.
Read the [threat model](docs/threat-model.md) for what is defended and what is accepted, and work
through the [hardening checklist](docs/hardening-checklist.md) before exposing an instance.

Main controls:

- **Passwords and sessions**: argon2id hashes, zxcvbn strength check, random 256-bit session
  tokens stored only as hashes, `__Host-` HttpOnly Secure SameSite=Lax cookies, rotation on every
  login and credential change, 7 day idle and 30 day absolute lifetime.
- **Two-factor authentication**: TOTP with replay protection and single-use recovery codes; the
  TOTP seeds are encrypted at rest (AES-256-GCM) under `HOJE_SECRET_KEY`.
- **CSRF**: the Origin must equal `HOJE_PUBLIC_URL` on every write, plus a per-session CSRF
  token; no CORS headers are sent.
- **Brute-force protection**: progressive lockouts per client address (IPv6 per /64), per account
  (capped at 15 minutes so a stranger cannot keep you out) and per trusted browser; a signed
  device cookie keeps a browser you already signed in with working while someone hammers your
  account. Structured `auth_failed` / `auth_locked` log lines feed CrowdSec or fail2ban.
- **Notifications**: an email after every password change or reset, 2FA disable and recovery-code
  regeneration, so a takeover does not go unnoticed.
- **Hard edges**: request bodies are capped at 1 MB (Caddy and the API), dates and ranges are
  bounded, `Cache-Control: no-store` on API responses, strict CSP and security headers, no API
  docs in production, and secrets, tokens and the query string never reach the logs.
- **Containers**: non-root, read-only filesystems, all capabilities dropped, the database and API
  on internal networks only.
- **Supply chain**: base images pinned by digest and patched at build time, locked dependencies,
  Dependabot, SHA-pinned GitHub Actions, and a release pipeline that publishes only the image it
  scanned (with provenance and an SBOM).

What you must set when deploying (details in the steps above and the checklist):

- `HOJE_SETUP_TOKEN` (before the first registration; remove it afterwards if you like).
- `TRUSTED_PROXIES`: required, the narrowest address of Nginx Proxy Manager as `hoje-web` sees it.
- The NPM **Advanced** block exactly as in step 4, including `client_max_body_size 1m;`.
- `HOJE_PUBLIC_URL` with `https://` (the API refuses to start in production otherwise),
  `HOJE_ALLOW_REGISTRATION=false`, and a pinned `HOJE_TAG` (for example `1.0.0`).
- A strong, backed-up `HOJE_SECRET_KEY`. Rotating it signs out nobody but invalidates the stored
  TOTP seeds (re-enrol 2FA with a recovery code), CSRF tokens and the trusted-device cookies.
- Encrypted off-host copies of the database dumps: dumps contain your data in plaintext.

## License

See [LICENSE](LICENSE).
