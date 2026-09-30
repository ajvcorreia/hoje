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

Automated testing and release pipelines run on every commit and tag.

> TODO (phase 7)

## Deployment: test VM

Running Hoje on the test VM for integration testing.

> TODO (phase 7)

## Deployment: production

Production deployment uses Caddy for automatic HTTPS, reverse proxying, and static file serving. Configuration and deployment steps.

> TODO (phase 7)

## Backup and restore

Automated daily backup with configurable retention. Restore procedures and point-in-time recovery.

> TODO (phase 7)

## Upgrades

Migrating between Hoje versions, including schema updates and data migrations.

> TODO (phase 8)

## Security

Security design including session management, CSRF protection, TOTP-based 2FA, rate limiting, and encryption at rest. Threat model and hardening checklist.

> TODO (phase 8)

## License

See [LICENSE](LICENSE).
