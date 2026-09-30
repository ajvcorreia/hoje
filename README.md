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

Local development environment setup.

> TODO (phase 1)

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
