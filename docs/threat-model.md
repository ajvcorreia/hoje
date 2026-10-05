# Hoje threat model

Scope: one self-hosted instance (`deploy/compose.prod.yml`) behind the owner's Nginx Proxy
Manager (NPM), one human user. Reviewed against `main` at Phase 8. The operational checklist
lives in [hardening-checklist.md](hardening-checklist.md).

## Assets

| Asset | Where | Impact if lost |
|---|---|---|
| Account (email, argon2id password hash) | `users` | Full access to everything below |
| Events, notes, leave, holidays | `events`, `leave_policies`, `holidays` | Privacy: plaintext in the DB and in every dump |
| TOTP secrets | `users.totp_secret_enc` (AES-256-GCM, AAD = user id, `security/crypto.py`) | 2FA bypass if `HOJE_SECRET_KEY` also leaks |
| Recovery codes | `recovery_codes.code_hash` (argon2id, single use) | 2FA bypass, 10 codes x 50 bits |
| Session cookie `__Host-hoje_session` | Browser; DB stores sha256 only (`services/sessions.py`) | Account takeover until logout/expiry (7 d idle, 30 d absolute) |
| `HOJE_SECRET_KEY` | `deploy/.env`, API/worker env | Decrypts TOTP secrets, forges CSRF tokens (`security/tokens.py`) |
| `POSTGRES_PASSWORD`, SMTP credentials | `deploy/.env`, container env | DB access; sending mail as the owner's domain |
| Backups | `/backups` volume of the worker (`hoje_backups` or `HOJE_BACKUP_DIR_HOST`; 0600, plaintext `pg_dump -Fc`) | Everything except TOTP seeds; a compromised worker can also delete them |
| Docker Hub token | GitHub Actions secret | Malicious image pushed to the tag production pulls |

## Trust boundaries

```
Internet --TLS--> NPM (host / container) --HTTP--> hoje-web (Caddy, :8080)
  --edge net--> api (uvicorn :8000) --backend net (internal)--> db
                worker --egress net--> SMTP relay
                worker --backend--> db (pg_dump) --> /backups volume (worker only)
Supply chain: GitHub Actions --> Docker Hub --> `docker compose pull` on the host
```

* NPM terminates TLS and is the only internet-facing listener. hoje-web is published on
  `127.0.0.1` or joined to NPM's Docker network; the API and DB are never published.
* Caddy trusts `X-Forwarded-For` only from `TRUSTED_PROXIES` (`trusted_proxies_strict`) and
  overwrites `X-Real-IP`; the API trusts `X-Real-IP` (`api/deps.py:client_ip`) and never XFF.
* The `backend` network is `internal: true` (no egress); only the worker and API reach SMTP.

## Actors

1. **Anonymous internet attacker**: scans, hits the login, forgot and register endpoints.
2. **Credential stuffer / password guesser**, possibly with a botnet or an IPv6 /64.
3. **Malicious site in the owner's browser**: CSRF, login CSRF, cross-origin reads, framing.
4. **Compromised LAN host or neighbouring container**: can reach published ports and Docker
   networks it shares, may forge proxy headers.
5. **Compromised dependency or CI action**: PyPI/npm package, base image, GitHub Action.

## Threats and existing mitigations (STRIDE)

| | Threat | Mitigation in this codebase |
|---|---|---|
| S | Password guessing | argon2id (`security/passwords.py`), zxcvbn >= 3 and 10-256 chars, progressive lockout 1 min doubling to 1 h with 24 h escalation memory per client address (IPv6 per /64) and per trusted device, per account capped at 15 min without escalation (`services/throttle.py`, `security/device.py`); `auth_failed` / `auth_locked` log events |
| S | Account enumeration | Dummy-hash verify for unknown emails, `202` for every forgot request with the lookup in a background task, account throttle keys for unknown emails too (`api/auth.py`) |
| S | 2FA bypass / replay | TOTP +-1 step with atomic compare-and-set on `totp_last_step` (`services/twofactor.py`), enrolment step burned, recovery codes argon2 + single use, MFA throttled per session and account |
| S | Session theft / fixation | 256-bit tokens hashed at rest, `__Host-` + Secure + HttpOnly + SameSite=Lax, rotation on login, MFA, password change/reset and 2FA changes (all other sessions deleted), mfa_pending sessions expire in 10 min |
| S | Reset token theft | 256-bit, sha256 at rest, 30 min, single use, older tokens voided, token in the URL fragment (never logged or sent as Referer), fragment stripped by `ResetPage.tsx` |
| T | CSRF / login CSRF | Origin (or Referer) must equal `HOJE_PUBLIC_URL` on every unsafe `/api/v1` request; HMAC per-session token required whenever a session exists (`api/deps.py:require_csrf`, attached to the whole router); no CORS headers |
| T | XSS / injection | React text rendering only, no `dangerouslySetInnerHTML`; QR as `data:` image; strict CSP (`deploy/Caddyfile`); ORM-only queries, LIKE escaping, bound `pg_notify` payload; Jinja autoescape for HTML mail; titles whitespace-collapsed in mail subjects and `EmailMessage` rejects CR/LF |
| T | Open redirect | `lib/safeNext.ts` (relative paths only, no `//`, `\`, control chars) |
| R | Untraceable abuse | Caddy JSON access log with resolved `client_ip`; `notification_log` of every email (no bodies or tokens) |
| I | Cross-user data access | Every service query filters on `user_id` (holidays via calendar ownership, reminders via event owner); SSE fan-out keyed by user id; SSE payloads carry ids only |
| T | Hostile import file (attacker-controlled input from an authenticated user) | The whole document is parsed by strict Pydantic models with the same bounds as the normal API (dates, lengths, palette, IANA zones, reminders), NUL and unencodable text rejected, global caps and a 10 MB body cap; unknown fields are ignored and no id from the file is ever used (all ids are generated server-side and every row is written with the caller's `user_id`, so a file cannot reference or modify another user's rows); validation finishes before the first write and the writes run in one savepoint-wrapped transaction, so any failure leaves nothing behind; errors name the item path but never echo content; imports are throttled (`import:user:{id}`, 10/hour, dry runs included) |
| E | Data destruction through a stolen session | `replace` re-checks the password (the `reauth:acct:{id}` lockout applies) and only soft-deletes: events and categories stay restorable for 30 days; `data_imported` / `data_exported` audit events carry the mode and counts only |
| I | Data exfiltration through a stolen session | Export contains only the caller's own live data and never credentials, TOTP secrets, recovery codes, sessions or ids; every export is logged (`data_exported`). A session thief can still download the account's calendar content, as they could read it in the UI |
| I | Secrets in logs / errors | structlog redaction of password/token/secret/cookie/code keys; validation errors never echo input; generic 500 body; docs UI off in production |
| I | Framing, sniffing, referrer leaks | `frame-ancestors 'none'`, `X-Frame-Options`, `nosniff`, `Referrer-Policy: same-origin`, COOP |
| D | Resource exhaustion | argon2 limited to 2 concurrent hashes, 400-day range cap on listings, 10 SSE streams per user, bounded subscriber queues, container `mem_limit`, read-only root FS, 1 MB request body cap (NPM, Caddy, API), 10 MB only on the import route (same three layers), import limited to 10 requests/hour per user with global caps (20 000 events, 100 categories, 2 000 custom holidays), bounded dates and event spans |
| E | Container escape / lateral movement | Non-root images (uid 10001), `cap_drop: ALL`, `no-new-privileges`, read-only FS, internal DB network, API not published, `--no-proxy-headers` |
| E | Supply chain | Lockfiles committed (`uv.lock`, `package-lock.json`), Actions pinned by SHA, base images pinned by digest and OS-patched at build, Dependabot, `permissions: contents: read`, no `pull_request_target`, release never runs on PRs, the scanned digest is the published image (Trivy gate before any tag moves, provenance + SBOM), pip-audit and npm audit in CI |

## Residual risks and accepted limitations

* **Single user, registration open until the first account exists.** Whoever registers first
  owns the instance. Mitigation is operational: NPM Access List until you have registered.
* **Account lockout can still inconvenience you, briefly.** Anyone who knows the owner's email
  can fill the per-account key, but that lock is capped at 15 minutes with no escalation memory,
  and a browser that already signed in (signed `hoje_device` cookie, 180 days) is throttled on its
  own key instead and is unaffected. A new browser or device waits out the lock; a password reset
  clears it. Existing sessions keep working. Rotating `HOJE_SECRET_KEY` invalidates the cookies.
* **Throttling is per address, IPv6 per /64.** A botnet still gets many keys; the per-account
  key, the device key and the password policy remain the real limit. CrowdSec/fail2ban at the
  edge helps (the API logs `auth_failed` / `auth_locked` for exactly that).
* **Request bodies are capped at 1 MB** by NPM (`client_max_body_size 1m`, operator setting),
  Caddy (`request_body max_size`) and the API itself (413 before reading, byte count for chunked).
  `/api/v1/import` alone takes 10 MB (Caddy `handle /api/v1/import`, `PATH_LIMITS` in
  `middleware.py`); the operator must raise NPM's limit to import files over 1 MB. A 10 MB JSON
  document is parsed in memory (tens of MB of Python objects) at most 10 times an hour per user.
* **Revocation latency for live sync.** An open SSE stream notices a revoked session at the next
  25 s check, so a logged-out tab can still receive change ids (never content) for up to ~50 s.
* **The API trusts `X-Real-IP`.** Anything that can reach `api:8000` directly (host processes,
  containers on the `edge` network) can choose its throttle identity.
* **Backups and the database are plaintext** apart from TOTP seeds. Disk or backup theft exposes
  all events, notes and password hashes. Off-host copies must be encrypted by the operator.
* **The worker holds the database password and can read, create and delete the local backups**
  (it runs `pg_dump` and owns the `/backups` volume). Compromising the worker therefore gives
  access to every dump and lets an attacker destroy them, so the encrypted off-host copy is the
  one that counts. The API cannot see the volume. The backup endpoints are owner-only and offer
  no download and no restore, so a stolen session can trigger (rate limited) backups but cannot
  exfiltrate the database through the app; `pg_dump` receives the password only in its
  environment, never on a command line or in logs.
* **`HOJE_SECRET_KEY` has no rotation support.** Changing it makes stored TOTP secrets
  undecryptable (sign in with a recovery code, then disable and re-enrol 2FA) and invalidates
  CSRF tokens of live sessions and the trusted-device cookies.
* **Audit trail is the log stream.** Security events (`auth_failed`, `auth_locked`,
  `auth_event`) are structured log lines kept only as long as Docker keeps the container log;
  there is no database audit table. Password changes and resets, 2FA disabling and recovery code
  regeneration email the owner (`notification_log` kind `security`), which only helps if the
  mailbox is not itself compromised and SMTP is configured.
* **Mail content is trusted to the relay.** Reminder emails contain event titles; SMTP uses
  STARTTLS with certificate checks only when configured so.
