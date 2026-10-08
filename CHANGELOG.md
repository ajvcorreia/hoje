# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.8] — 2026-10-08

### Added

- A "Light (high contrast)" theme (Settings › Appearance): pure white surfaces, black text,
  darker borders and month outlines, a thicker focus ring, outlined events and holidays, and a
  category palette where every event text/fill pair reaches WCAG AAA (7:1). Light, Dark and System
  are unchanged.
- Eight more category colours (rose, fuchsia, purple, sky, emerald, yellow, brown, gray; 20 in
  total) in the colour picker, in all three themes. Migration 0008 widens the colour constraint;
  rolling it back turns categories using a new colour into slate.

## [1.3.7] — 2026-10-08

### Added

- Settings › "Vertical event text size" (10–32 px, default 12, stored per user like "Events shown
  per day", `vertical_text_size` on `PATCH /api/v1/me`, included in export/import; migration 0007).
  Rotated multi-day labels use that size and shrink only when the name does not fit the event's
  height; the narrow rotated column widens with the size. A name that cannot fit even at the
  minimum size is still drawn as a horizontal title.

## [1.3.6] — 2026-10-08

### Changed

- Month grid: events are always packed to the left of the day with no gaps, and the last one
  fills the cell to the right edge. Rotated multi-day labels use only their own narrow column
  (first, hard left) instead of spreading across the width of a horizontal event lane, and other
  events no longer leave an empty slot next to them. Month columns are sized from the widest
  single day.

## [1.3.5] — 2026-10-08

### Changed

- Rotated multi-day labels now sit first in the month column, hard left right after the day
  number, ahead of the holiday / birthday text and the horizontal events, instead of drifting
  towards the middle of a wide column.

### Fixed

- Version 1.3.4 accidentally contained six stray temporary files; they are removed.

## [1.3.4] — 2026-10-08

### Fixed

- Event, birthday and holiday names are never cut off or shortened: month columns are re-measured
  once web fonts have loaded and count the lane border, the ellipsis and clipping are gone, and a
  rotated multi-day label whose name does not fit the block height is shown as a normal
  horizontal title instead. The agenda, search results, day list, holiday list and vacation pill
  no longer truncate either.

## [1.3.3] — 2026-10-08

### Changed

- "Events shown per day" is now stored per user in the database (migration 0006,
  `max_events_per_day` on `PATCH /api/v1/me`, included in export/import) instead of per device, so
  it follows you to every machine. It starts at 2; set it again in Settings after upgrading.
- Month grid: events, birthdays and holidays are always horizontal and share one row with the day
  number; the month column grows wider to fit them instead of rows growing taller, so only
  horizontal scrolling is needed. Rotated multi-day labels work for any limit (1–6) and their
  width counts towards the column width.

## [1.3.2] — 2026-10-08

### Added

- Settings › Appearance › "Events shown per day" (1–6, default 2, per device). Events beyond the
  limit are still counted as "+N".

### Changed

- Birthdays and holidays stay visible on days that also have events, as a text line above the
  events instead of a small corner mark.
- A month column holding only rotated (vertical) event labels now shrinks to the width those
  labels need.

### Fixed

- A calendar tab left open for a long time no longer goes stale: it refetches when the tab becomes
  visible, regains focus or the browser comes back online (plus a 5-minute safety refetch while
  visible), and "today" rolls over at midnight without a reload.

## [1.3.1] — 2026-10-06

### Fixed

- Pointing the FelizAnniv sync at FelizAnniv's web page (which answers every path with its HTML
  page) now says so and asks for the backend address (usually port 4000), instead of "FelizAnniv
  sent a response Hoje does not understand". The Settings hint and README now ask for the backend
  address rather than "the address you open FelizAnniv at".

## [1.3.0] — 2026-10-05

### Added

- Birthdays from FelizAnniv: Settings › FelizAnniv birthdays connects your FelizAnniv server with
  its address and an API key (FelizAnniv Settings › API Keys). Hoje tests the connection before
  saving, stores the key encrypted (only a short hint is ever shown) and syncs one way, FelizAnniv
  to Hoje, every 6 hours or on "Sync now". Birthdays appear read-only on the calendar like
  holidays ("🎂 Ana (34)"; 29 February on the 28th in other years) in the month grid, year view,
  agenda, day popover and the mobile views, with a per-device "Show birthdays" switch and a
  Birthdays chip. They are not events: no reminders, no leave or working-day effect, not exported.
- API: `GET/PUT/DELETE /api/v1/integrations/felizanniv`, `POST /api/v1/integrations/felizanniv/sync`
  and `GET /api/v1/birthdays?from&to`; realtime entity `birthday`. Migration 0005 adds
  `felizanniv_integrations` and `birthdays`.
- `HOJE_INTEGRATION_ALLOWED_PRIVATE_CIDRS`: private networks the sync may reach (empty by default:
  public addresses only). Every outbound request goes through a new SSRF guard: loopback,
  link-local and metadata addresses are always refused, Hoje's own container networks too (unless
  an exact address is listed), the resolved address is pinned against DNS rebinding, redirects are
  not followed and responses are limited to 10 s and 5 MiB per page.

### Changed

- The worker of `deploy/compose.test.yml` joins a new `egress` network so it can reach
  FelizAnniv; in `deploy/compose.prod.yml` it already had one.
- `httpx` is now a runtime dependency of the API image; its per-request log lines are silenced.

### Upgrade notes

- To sync from a FelizAnniv on your LAN, set `HOJE_INTEGRATION_ALLOWED_PRIVATE_CIDRS` in
  `deploy/.env` (for example `192.168.10.0/24`, or better the FelizAnniv host as `/32`) and
  recreate `api` and `worker`. Nothing to do otherwise.

## [1.2.0] — 2026-10-05

### Added

- Export and import of your data. Settings › Your data downloads categories, events with their
  reminders, leave allowances, holiday calendar settings and your changes to the bundled holidays,
  time zone and weekend days as one JSON file (`GET /api/v1/export`; format in
  `docs/export-format.md`). Passwords, two-factor secrets, recovery codes and sessions are never
  included.
- Import (`POST /api/v1/import`): the whole file is validated with the API's own bounds, previewed with a
  dry run, then applied in one transaction with a precise error path (for example
  `events[57].end_date`) when something is wrong. **Merge** reuses categories by name and skips
  duplicate events; **replace** asks for your password and moves the current events and categories
  to the bin first. Limited to 10 imports per hour, 20 000 events and 10 MB per file; one realtime
  change refreshes open browsers. Audit log events `data_exported` and `data_imported` (mode and
  counts only).

### Changed

- The request body limit is now per route: 10 MiB for `/api/v1/import` (Caddy and API), 1 MiB
  everywhere else as before. If you use Nginx Proxy Manager, set `client_max_body_size 10m` in its
  Advanced block to import files over 1 MB.
- Restoring a binned event whose category was binned too (after a replace import) brings the
  category back when no live category has taken its name.

## [1.1.0] — 2026-10-05

### Added

- Database backups run inside the app. The worker dumps the database every night
  (`BACKUP_SCHEDULE_HOUR`, in `TZ`) with `pg_dump -Fc`, verifies and fsyncs each dump, keeps
  `BACKUP_KEEP_DAYS` days and records every run in the new `backup_runs` table (migration 0004).
  A missed schedule is made up for when the worker starts; two workers never back up at once.
  New settings: `HOJE_BACKUP_ENABLED`, `HOJE_BACKUP_DIR`, `BACKUP_SCHEDULE_HOUR`,
  `BACKUP_KEEP_DAYS`, `TZ`.
- Settings › Backups (instance owner only): last backup, schedule, recent runs with errors,
  a "Back up now" button and a warning when the last backup is older than 26 hours. Backed by
  `GET /api/v1/backups` and `POST /api/v1/backups`; updates live through the realtime stream.
  There is deliberately no download or restore endpoint: restores stay a command-line operation.

### Changed

- The separate `backup` container and `deploy/backup/backup.sh` are removed. The `hoje-api`
  image now ships the PostgreSQL 17 client (`pg_dump`, `pg_restore` from the official PGDG
  repository), and the worker mounts the backups volume at `/backups` (the API does not).
- `HOJE_BACKUP_DIR` now names the directory inside the container; a host path for the backups is
  `HOJE_BACKUP_DIR_HOST` in `deploy/.env`.
- A failed backup no longer shows up as an unhealthy container; it is visible in Settings ›
  Backups and in the worker log (`backup_failed`).
- Restore guide, hardening checklist and threat model updated: the worker can now read and delete
  the local dumps, so encrypted off-host copies matter more.

### Upgrade notes

- Delete the old `backup` service from your compose file (or use the new
  `deploy/compose.prod.yml`) and rename `HOJE_BACKUP_DIR` to `HOJE_BACKUP_DIR_HOST` if you set it.
- Existing dumps stay in the `hoje_backups` volume (or your host directory). Give them to the
  app user once so the worker can write and prune there:
  `docker run --rm -v hoje_backups:/b alpine chown -R 10001:10001 /b` (host directory:
  `sudo chown -R 10001:10001 <dir>`). See `deploy/backup/restore.md`.
- The worker takes a first backup when it starts, because it has no record of an earlier one.

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
