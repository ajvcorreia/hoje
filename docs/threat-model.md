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
| Backups | `hoje_backups` volume / `HOJE_BACKUP_DIR` (0600, plaintext `pg_dump -Fc`) | Everything except TOTP seeds |
| Docker Hub token | GitHub Actions secret | Malicious image pushed to the tag production pulls |

## Trust boundaries

```
Internet --TLS--> NPM (host / container) --HTTP--> hoje-web (Caddy, :8080)
  --edge net--> api (uvicorn :8000) --backend net (internal)--> db
                worker --egress net--> SMTP relay        backup --backend--> db
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
| S | Password guessing | argon2id (`security/passwords.py`), zxcvbn >= 3 and 10-256 chars, per-IP and per-account progressive lockout 1 min doubling to 1 h with 24 h escalation memory (`services/throttle.py`) |
| S | Account enumeration | Dummy-hash verify for unknown emails, `202` for every forgot request with the lookup in a background task, account throttle keys for unknown emails too (`api/auth.py`) |
| S | 2FA bypass / replay | TOTP +-1 step with atomic compare-and-set on `totp_last_step` (`services/twofactor.py`), enrolment step burned, recovery codes argon2 + single use, MFA throttled per session and account |
| S | Session theft / fixation | 256-bit tokens hashed at rest, `__Host-` + Secure + HttpOnly + SameSite=Lax, rotation on login, MFA, password change/reset and 2FA changes (all other sessions deleted), mfa_pending sessions expire in 10 min |
| S | Reset token theft | 256-bit, sha256 at rest, 30 min, single use, older tokens voided, token in the URL fragment (never logged or sent as Referer), fragment stripped by `ResetPage.tsx` |
| T | CSRF / login CSRF | Origin (or Referer) must equal `HOJE_PUBLIC_URL` on every unsafe `/api/v1` request; HMAC per-session token required whenever a session exists (`api/deps.py:require_csrf`, attached to the whole router); no CORS headers |
| T | XSS / injection | React text rendering only, no `dangerouslySetInnerHTML`; QR as `data:` image; strict CSP (`deploy/Caddyfile`); ORM-only queries, LIKE escaping, bound `pg_notify` payload; Jinja autoescape for HTML mail; titles whitespace-collapsed in mail subjects and `EmailMessage` rejects CR/LF |
| T | Open redirect | `lib/safeNext.ts` (relative paths only, no `//`, `\`, control chars) |
| R | Untraceable abuse | Caddy JSON access log with resolved `client_ip`; `notification_log` of every email (no bodies or tokens) |
| I | Cross-user data access | Every service query filters on `user_id` (holidays via calendar ownership, reminders via event owner); SSE fan-out keyed by user id; SSE payloads carry ids only |
| I | Secrets in logs / errors | structlog redaction of password/token/secret/cookie/code keys; validation errors never echo input; generic 500 body; docs UI off in production |
| I | Framing, sniffing, referrer leaks | `frame-ancestors 'none'`, `X-Frame-Options`, `nosniff`, `Referrer-Policy: same-origin`, COOP |
| D | Resource exhaustion | argon2 limited to 2 concurrent hashes, 400-day range cap on listings, 10 SSE streams per user, bounded subscriber queues, container `mem_limit`, read-only root FS |
| E | Container escape / lateral movement | Non-root images (uid 10001), `cap_drop: ALL`, `no-new-privileges`, read-only FS, internal DB network, API not published, `--no-proxy-headers` |
| E | Supply chain | Lockfiles committed (`uv.lock`, `package-lock.json`), Actions pinned by SHA, `permissions: contents: read`, no `pull_request_target`, release never runs on PRs, Trivy gate before push, pip-audit and npm audit in CI |

## Residual risks and accepted limitations

* **Single user, registration open until the first account exists.** Whoever registers first
  owns the instance. Mitigation is operational: NPM Access List until you have registered.
* **Account lockout is a denial of service.** Anyone who knows the owner's email can keep the
  account key locked (one wrong password per hour after escalation). Existing sessions keep
  working; a password reset clears the lock but it can be re-armed. Tracked as finding S-02.
* **Per-IP throttling is per address.** An IPv6 /64 or a botnet gets many keys; the per-account
  key and the password policy remain the real limit. CrowdSec/fail2ban at the edge helps.
* **Unbounded request bodies** reach the API unless Caddy or NPM caps them (finding S-01).
* **Revocation latency for live sync.** An open SSE stream notices a revoked session at the next
  25 s check, so a logged-out tab can still receive change ids (never content) for up to ~50 s.
* **The API trusts `X-Real-IP`.** Anything that can reach `api:8000` directly (host processes,
  containers on the `edge` network) can choose its throttle identity.
* **Backups and the database are plaintext** apart from TOTP seeds. Disk or backup theft exposes
  all events, notes and password hashes. Off-host copies must be encrypted by the operator.
* **`HOJE_SECRET_KEY` has no rotation support.** Changing it makes stored TOTP secrets
  undecryptable (sign in with a recovery code, then disable and re-enrol 2FA) and invalidates
  CSRF tokens of live sessions.
* **No security notifications or audit trail** for password changes, resets or 2FA changes
  (findings S-06, S-07).
* **Mail content is trusted to the relay.** Reminder emails contain event titles; SMTP uses
  STARTTLS with certificate checks only when configured so.
