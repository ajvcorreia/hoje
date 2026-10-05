# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] — 2026-10-05

### Fixed

- The app now reports its real version (the API, its OpenAPI document and `hoje.__version__`
  still said 0.1.0 in the 1.0.0 images; image tags and labels were already correct).

## [1.0.0] — 2026-10-05

### Added

- Optional `HOJE_SETUP_TOKEN`: while no account exists, the first registration requires it.
- Security notification emails after a password change or reset, turning 2FA off, and
  regenerating recovery codes.
- Structured security logs (`auth_failed`, `auth_locked`, `auth_event`) for CrowdSec or fail2ban.
- Threat model (`docs/threat-model.md`) and internet-exposure hardening checklist
  (`docs/hardening-checklist.md`).
- Dependabot for GitHub Actions, Docker images, Python and npm dependencies.
- Mobile test coverage for holiday cards and dots, the vacation balance sheet and week numbers.

### Changed

- Vertical event names read bottom-to-top and shrink to fit the height of their block.
- Each month column's minimum width follows its widest title (three day-number widths when it has
  no text); the "Fit columns to text" setting was removed.
- Base images are pinned by digest and receive OS security updates at build time.
- Releases push exactly the image that was scanned, with build provenance and an SBOM.
- `TRUSTED_PROXIES` is required by the production compose file.
- Email delivery log entries older than 180 days are deleted by the daily housekeeping.

### Fixed

- A live-sync connection that failed before sending anything could keep counting toward the
  10-stream limit.
- Dates near the representable limits could cause server errors; dates are now limited to
  1900–2200 and single events to 366 days.

### Security

- Request bodies are capped at 1 MB in Caddy and in the API, so oversized uploads can no longer
  exhaust the API's memory.
- Browsers that signed in before carry a signed device cookie, so strangers failing logins against
  the account cannot lock the owner out; account-wide lockouts are capped at 15 minutes.
- IPv6 clients are throttled per /64 network.
- API responses are sent with `Cache-Control: no-store`; the OpenAPI schema is not served in
  production; SQL parameters are kept out of logs; Caddy's access log no longer records cookies,
  CSRF tokens or query strings.
- Production requires an `https://` `HOJE_PUBLIC_URL`.
- A test guarantees every state-changing API route keeps its CSRF and login protection.

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
- Search events by title (case-insensitive, trigram-indexed).
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
