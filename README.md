# Hoje

A self-hosted personal planner replacing a spreadsheet, with a desktop month-column grid and mobile day view. Track vacation balance, view Portugal and UAE holidays, receive email reminders, enable two-factor authentication, and sync changes live across devices.

## Features

> TODO (phase 3)

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
`web` (Caddy serving the SPA and proxying `/api`) and a nightly `backup` service. TLS is terminated
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
(`POSTGRES_PASSWORD`). Set `DOCKERHUB_NAMESPACE`, `HOJE_TAG`, the SMTP settings and:

- `HOJE_PUBLIC_URL`: the **https** URL users type (`https://hoje.example.com`). Cookies are
  `Secure` and the Origin check compares against it, so a wrong value breaks sign-in.
- `TRUSTED_PROXIES`: the IP or CIDR NPM connects from, as seen by `hoje-web` (see below).
- `TZ` and `BACKUP_SCHEDULE_HOUR` for the backup time.

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
  ```

  Live sync across devices streams events over one long-lived response: without
  `proxy_buffering off` Nginx holds the events back, and the default 60 s `proxy_read_timeout`
  would cut the stream (the app reconnects, but updates would lag). The `X-Forwarded-For` line
  makes NPM pass the real client address on, which `hoje-web` resolves against `TRUSTED_PROXIES`.

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

The `backup` service dumps the database nightly at `BACKUP_SCHEDULE_HOUR` (local `TZ`) with
`pg_dump -Fc`, verifies the dump, and keeps `BACKUP_KEEP_DAYS` days (default 14) in the
`hoje_backups` volume, or in `HOJE_BACKUP_DIR` if set. It reports `unhealthy` in `docker compose ps`
if no backup has succeeded for 26 hours.

```bash
$DC exec backup sh /backup/backup.sh now     # an immediate backup
```

Restore steps (stop `web`/`api`/`worker`, `pg_restore --clean --if-exists`, start) and how to copy
dumps off the host are in [deploy/backup/restore.md](deploy/backup/restore.md). Keep copies on
another machine: a dump on the same disk does not survive losing the host.

## Upgrades

1. Take a backup: `$DC exec backup sh /backup/backup.sh now`.
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

## Security

Security design including session management, CSRF protection, TOTP-based 2FA, rate limiting, and encryption at rest. Threat model and hardening checklist.

> TODO (phase 8)

## License

See [LICENSE](LICENSE).
