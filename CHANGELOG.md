# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-10-05

### Added

- Setup token requirement for initial user registration (disabled after first account exists).
- Security event logging and notification emails for password changes, 2FA updates, and recovery code regeneration.
- Structured `auth_failed` and `auth_locked` log lines for integration with CrowdSec or fail2ban.
- Trusted-device lockout relief: a signed device cookie allows already-signed-in browsers to work while per-IP login attempts are throttled.
- IPv6 throttling per /64 subnet instead of full IPv6 address.
- Date bounds validation to prevent invalid event dates and ranges.
- Request body size caps (1 MB) at Caddy and API layers.
- `Cache-Control: no-store` header on all API responses.
- OpenAPI documentation endpoint disabled in production.
- Security headers on error responses (Caddy).
- Mobile test coverage for holiday cards, vacation balance sheet, and week-number column toggle.

### Changed

- Vertical event names now read bottom-to-top and shrink to fit their block width (improved readability).
- "Fit columns to text" setting was removed; column widths now always follow the text.
- Base container images are pinned by digest and patched at build time during release.

### Fixed

- SSE subscription releases properly even if the stream never starts.
- SQL query parameters no longer appear in logs.
- Image vulnerability scanning and provenance in the release pipeline.

### Security

- Enforced HTTPS public URL in production (`HOJE_PUBLIC_URL` must begin with `https://`).
- Dropped all Linux capabilities and run containers as non-root.
- Read-only root filesystem for all containers.
- Dependabot enabled for automated dependency updates.
- Software Bill of Materials (SBOM) and build provenance published with releases.
- Docker images signed and scanned by Trivy before release.

## [0.7.0] — 2026-10-03

### Added

- Production deployment behind Nginx Proxy Manager with TLS termination.
- Nightly backup service with retention policy and restore instructions.
- Smoke test suite covering registration, 2FA, event creation, live sync, email delivery, and security header validation.
- Release pipeline publishing images to Docker Hub with SHA and version tags.
- GitHub Actions CI/CD workflows for testing, building, and releasing.

### Changed

- Production compose stack (`compose.prod.yml`) with PostgreSQL, API, worker, web, and backup services.

### Fixed

- Login throttle now keys on trusted `X-Real-IP` (passed by Caddy from `TRUSTED_PROXIES`) instead of spoofable `X-Forwarded-For`.
- Vertical event names shrink to fit their column width.
- Month column minimum width follows its widest text.

## [0.6.0] — 2026-10-03

### Added

- Email reminder delivery: due-time calculation, scheduling, claiming with `FOR UPDATE SKIP LOCKED`, and retry logic (1, 5, 30, 120 min).
- Reminder bell icon and SMTP configuration hint in the frontend.
- Daily worker housekeeping and fast E2E test interval.

### Fixed

- Reminder logs redact sensitive fields but record action counts.
- Vertical event names display bottom-to-top.

## [0.5.0] — 2026-10-02

### Added

- Vacation balance pill showing used, planned, and remaining days for the calendar year.
- Vacation balance settings and leave policy management (allowance and carried-over days).
- Holiday calendar support for Portugal (PT) and United Arab Emirates (AE) with working-day counting.
- Working-day arithmetic: excludes weekends (configurable per user) and enabled non-working holidays.
- Leave impact preview on event creation/editing.
- Fit columns to text: column widths automatically adjust to their content.
- Event leave_impact field indicates which leave events affect vacation balance.
- Text size setting (small, normal, large).
- Week number display in the calendar.
- Per-event vertical label flag for multi-day event visibility.

### Changed

- Calendar outline styling: outlined months with centered month names.
- Past days can be struck through (user-configurable).

## [0.4.0] — 2026-10-02

### Added

- Live sync across devices over Server-Sent Events (SSE) with Postgres `LISTEN/NOTIFY`.
- Real-time change warnings in the event editor when another device modifies the event.
- Live sync status pill in the calendar header.
- Vertical event names for multi-day events (improves visibility on crowded days).

## [0.3.0] — 2026-10-02

### Added

- Mobile day and month calendar views optimized for phones.
- Mobile quick add with click-type-Enter flow.
- View persistence (remembered settings per device).
- Playwright end-to-end test suite covering auth, event creation, same-day layout, and mobile views.
- Isolated throwaway compose stack for E2E testing.

### Fixed

- Event editor day popover focus after visibility change.
- Auth flow in open-registration mode.

## [0.2.0] — 2026-10-02

### Added

- Desktop month grid: 12 months side by side, weekday-aligned rows, weekends shaded, today highlighted.
- Year and Agenda views for alternate calendar layouts.
- Event search with full-text indexing (GIN trgm).
- Event and category API with category management and colour palette (12 fixed keys).
- Month layout pure function with lane assignment for visual rendering.
- Toast, popover, and sheet-capable dialog primitives for the UI.
- Date helper utilities and Recurrence expansion (monthly, yearly) with `repeat_until` support.
- Category filter chips.

### Changed

- Regenerated API types from OpenAPI schema.

## [0.1.1] — 2026-09-30

### Added

- Authentication with email and password using Argon2id hashing.
- Two-factor authentication (TOTP) with recovery codes.
- User registration and login with CSRF protection.
- Session management with rotating tokens, 7-day idle timeout, and 30-day absolute lifetime.
- Password reset flow with time-limited tokens.
- Me endpoint for user profile and settings.
- Security primitives: AES-GCM encryption for TOTP secrets, zxcvbn password strength check, secure session cookies (`__Host-`, HttpOnly, Secure, SameSite=Lax).
- Progressive login lockouts per client address, per account, and per trusted device.
- Email notifications for password changes, 2FA updates, and recovery code regeneration.
- Comprehensive auth test coverage (registration, login, 2FA, recovery codes, password reset, lockouts).

### Changed

- Frontend auth data layer and UI primitives for authentication screens.
- Settings sections for account, security, email, and sessions.
- Route guards and user menu.

## [0.1.0] — 2026-09-30

### Added

- FastAPI backend with SQLAlchemy async, PostgreSQL 17, and Alembic migrations.
- React 19 frontend with Vite, Tailwind CSS, TanStack Query, and openapi-fetch.
- Caddy web server serving the SPA and proxying `/api`.
- Docker Compose for development (with hot reload) and testing stacks.
- CI workflow: backend lint/format/test, frontend lint/typecheck/test/build, Docker Trivy scans, dependency audits.
- Documentation of architecture, API contract, database schema, and working conventions in [docs/PLAN.md](docs/PLAN.md).
- Docker image security: non-root, read-only filesystem, capabilities dropped.
- Structured JSON logging with structlog.
