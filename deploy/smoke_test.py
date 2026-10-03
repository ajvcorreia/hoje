#!/usr/bin/env python3
"""Post-deploy smoke test for a FRESH Hoje stack (no accounts yet). Standard library only.

    python3 deploy/smoke_test.py BASE_URL MAILPIT_URL [ORIGIN]

BASE_URL     where the web tier answers (for example http://e2e-web:8080)
MAILPIT_URL  Mailpit's HTTP API; the stack's SMTP must point at it (reminder mail is checked)
ORIGIN       the stack's HOJE_PUBLIC_URL, sent as the Origin header (default: BASE_URL)

It registers the first account, so run it only against a throwaway stack. The last check
deliberately trips the per-IP login lock, so nothing else should be done from this client IP
for a minute afterwards. Prints PASS/FAIL per check; exits 1 if any check failed.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import http.client
import http.cookiejar
import json
import struct
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

EMAIL = "smoke@example.com"
PASSWORD = "correct horse battery staple 42"  # noqa: S105 - throwaway stack only
REMINDER_TIMEOUT = 180
SSE_TIMEOUT = 5

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, info: str = "") -> bool:
    results.append((name, bool(ok), info))
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f"  [{info}]" if info and not ok else ""), flush=True)
    return bool(ok)


class Client:
    """One browser-like session: cookie jar, Origin and CSRF headers."""

    def __init__(self, base: str, origin: str) -> None:
        self.base = base.rstrip("/")
        self.origin = origin
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf: str | None = None

    def req(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        csrf: bool = True,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], Any]:
        h = {"Content-Type": "application/json"}
        if method != "GET":
            h["Origin"] = self.origin
            if csrf and self.csrf:
                h["X-CSRF-Token"] = self.csrf
        h.update(headers or {})
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with self.opener.open(request, timeout=20) as resp:
                raw = resp.read()
                return resp.status, dict(resp.headers), _json(raw)
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), _json(exc.read())

    def state(self) -> dict[str, Any]:
        _, _, s = self.req("GET", "/api/v1/auth/state")
        self.csrf = s.get("csrf_token")
        return s

    def cookie_header(self) -> str:
        return "; ".join(f"{c.name}={c.value}" for c in self.jar)


def _json(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return raw.decode(errors="replace")


def totp(secret: str, at: float) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", int(at) // 30), hashlib.sha1).digest()
    off = digest[-1] & 0x0F
    return f"{(struct.unpack('>I', digest[off:off + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def next_step_code(secret: str, last: list[int]) -> str:
    """A code from a fresh 30 s step (the server rejects replays of a used step)."""
    while int(time.time()) // 30 <= last[0]:
        time.sleep(1)
    last[0] = int(time.time()) // 30
    return totp(secret, time.time())


class SseListener(threading.Thread):
    """Reads /api/v1/realtime/stream with its own connection and the given session cookie."""

    def __init__(self, base: str, cookie: str) -> None:
        super().__init__(daemon=True)
        self.url = urllib.parse.urlsplit(base)
        self.cookie = cookie
        self.frames: list[tuple[str, Any]] = []
        self.status: int | None = None
        self.connected = threading.Event()
        self.cond = threading.Condition()
        self.conn: http.client.HTTPConnection | None = None
        self._halt = False

    def run(self) -> None:
        cls = http.client.HTTPSConnection if self.url.scheme == "https" else http.client.HTTPConnection
        port = self.url.port or (443 if self.url.scheme == "https" else 80)
        self.conn = cls(self.url.hostname, port, timeout=60)
        try:
            self.conn.request(
                "GET",
                "/api/v1/realtime/stream",
                headers={"Cookie": self.cookie, "Accept": "text/event-stream"},
            )
            resp = self.conn.getresponse()
            self.status = resp.status
            self.connected.set()
            event, data = "message", []
            while not self._halt:
                line = resp.readline()
                if not line:
                    break
                text = line.decode().rstrip("\r\n")
                if text == "":
                    if data:
                        with self.cond:
                            self.frames.append((event, _json("\n".join(data).encode())))
                            self.cond.notify_all()
                    event, data = "message", []
                elif text.startswith("event:"):
                    event = text[6:].strip()
                elif text.startswith("data:"):
                    data.append(text[5:].strip())
        except (OSError, AttributeError, ValueError, http.client.HTTPException):
            pass
        finally:
            self.connected.set()

    def wait_for(self, op: str, event_id: str, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self.cond:
            while True:
                for name, payload in self.frames:
                    if (
                        name == "change"
                        and isinstance(payload, dict)
                        and payload.get("entity") == "event"
                        and payload.get("op") == op
                        and payload.get("id") == event_id
                    ):
                        return True
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self.cond.wait(left)

    def close(self) -> None:
        self._halt = True
        if self.conn is not None:
            self.conn.close()


class Mailpit:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def messages(self) -> list[dict[str, Any]]:
        with urllib.request.urlopen(self.base + "/api/v1/messages?limit=200", timeout=15) as r:
            return json.loads(r.read()).get("messages", [])

    def reminders_for(self, title: str) -> list[dict[str, Any]]:
        return [
            m
            for m in self.messages()
            if str(m.get("Subject", "")).startswith("Reminder:") and title in str(m.get("Subject", ""))
        ]


def run(base: str, mailpit_url: str, origin: str) -> None:
    anon = Client(base, origin)

    # --- probes and headers ------------------------------------------------------------
    st, _, _ = anon.req("GET", "/healthz")
    check("GET /healthz is 200", st == 200, str(st))
    st, _, body = anon.req("GET", "/readyz")
    check("GET /readyz is 200", st == 200, f"{st} {body}")

    for label, path in (("SPA /", "/"), ("API /api/v1/auth/state", "/api/v1/auth/state")):
        st, hdr, _ = anon.req("GET", path)
        low = {k.lower(): v for k, v in hdr.items()}
        csp = low.get("content-security-policy", "")
        check(f"{label}: Content-Security-Policy with frame-ancestors 'none'", "frame-ancestors 'none'" in csp, csp[:80])
        check(f"{label}: X-Frame-Options DENY", low.get("x-frame-options", "").upper() == "DENY")
        check(f"{label}: no Server header", "server" not in low, low.get("server", ""))

    # --- registration, login, 2FA -------------------------------------------------------
    a = Client(base, origin)
    s = a.state()
    if not check("fresh stack: registration is open", s.get("registration_open") is True, str(s)):
        return
    st, _, _ = a.req("POST", "/api/v1/auth/register", {"email": EMAIL, "password": PASSWORD})
    check("register the first user (201)", st == 201, str(st))
    s = a.state()
    check("registered user is signed in", s.get("authenticated") is True)
    st, _, _ = a.req("POST", "/api/v1/auth/logout")
    check("logout (204)", st == 204, str(st))
    a.state()
    st, _, body = a.req("POST", "/api/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
    check("login with password", st == 200 and body.get("status") == "ok", f"{st} {body}")
    a.state()

    st, _, setup = a.req("POST", "/api/v1/auth/2fa/setup", {"password": PASSWORD})
    check("2FA setup returns a secret", st == 200 and bool(setup.get("secret")), str(st))
    secret = setup["secret"]
    last = [int(time.time()) // 30 - 2]
    st, _, rc = a.req("POST", "/api/v1/auth/2fa/enable", {"code": next_step_code(secret, last)})
    check("2FA enabled with a TOTP code (10 recovery codes)", st == 200 and len(rc.get("recovery_codes", [])) == 10, str(st))
    a.state()
    a.req("POST", "/api/v1/auth/logout")

    b = Client(base, origin)
    st, _, body = b.req("POST", "/api/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
    check("login now asks for MFA", st == 200 and body.get("status") == "mfa_required", f"{st} {body}")
    b.state()
    code = next_step_code(secret, last)
    st, _, body = b.req("POST", "/api/v1/auth/login/mfa", {"code": code})
    check("MFA login with TOTP", st == 200 and body.get("status") == "ok", f"{st} {body}")
    b.state()

    # --- events and live sync -----------------------------------------------------------
    today = dt.datetime.now(dt.UTC).date().isoformat()
    st, _, created = b.req("POST", "/api/v1/events", {"title": "Smoke default category", "start_date": today})
    ok = st == 201 and bool(created and created.get("event", {}).get("category_id"))
    check("create an event with the default category", ok, f"{st} {created}")

    listener = SseListener(base, b.cookie_header())
    listener.start()
    listener.connected.wait(10)
    check("SSE stream opens (200)", listener.status == 200, str(listener.status))
    time.sleep(0.5)  # let the hub register the subscriber
    st, _, created = b.req("POST", "/api/v1/events", {"title": "Smoke live sync", "start_date": today})
    event = (created or {}).get("event", {}) if st == 201 else {}
    check("SSE: 'create' change frame within 5 s", bool(event) and listener.wait_for("create", event.get("id", ""), SSE_TIMEOUT))
    if event:
        st, _, upd = b.req("PATCH", f"/api/v1/events/{event['id']}", {"title": "Smoke live sync 2", "version": event["version"]})
        check("SSE: 'update' change frame within 5 s", st == 200 and listener.wait_for("update", event["id"], SSE_TIMEOUT), str(st))
    listener.close()

    # --- reminder email -----------------------------------------------------------------
    mail = Mailpit(mailpit_url)
    start = (dt.datetime.now(dt.UTC) + dt.timedelta(minutes=2)).replace(second=0, microsecond=0)
    end = start + dt.timedelta(minutes=30)
    title = f"Smoke reminder {int(time.time())}"
    st, _, created = b.req(
        "POST",
        "/api/v1/events",
        {
            "title": title,
            "start_date": start.date().isoformat(),
            "all_day": False,
            "start_time": start.strftime("%H:%M:%S"),
            "end_date": end.date().isoformat(),
            "end_time": end.strftime("%H:%M:%S"),
            "timezone": "UTC",
            "reminders": [{"offset_minutes": 1}],
        },
    )
    check("create a timed event with a 1-minute reminder", st == 201, f"{st} {created}")
    deadline = time.monotonic() + REMINDER_TIMEOUT
    found: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        found = mail.reminders_for(title)
        if found:
            break
        time.sleep(3)
    check(f"reminder email arrives in Mailpit within {REMINDER_TIMEOUT} s", bool(found), "none seen")
    if found:
        time.sleep(5)  # a duplicate would show up shortly after the first
        count = len(mail.reminders_for(title))
        check("exactly one reminder email for the event", count == 1, f"{count} emails")

    # --- client IP handling (last: it trips the per-IP login lock) ---------------------
    spoof = Client(base, origin)
    codes: list[int] = []
    last_headers: dict[str, str] = {}
    for i in range(8):
        st, last_headers, _ = spoof.req(
            "POST",
            "/api/v1/auth/login",
            {"email": f"ghost{i}@example.com", "password": "wrong password " * 2},
            headers={"X-Forwarded-For": f"203.0.113.{10 + i}", "X-Real-IP": f"198.51.100.{10 + i}"},
        )
        codes.append(st)
        if st == 429:
            break
    low = {k.lower(): v for k, v in last_headers.items()}
    check(
        "forged X-Forwarded-For / X-Real-IP cannot dodge the per-IP lock",
        codes[-1] == 429 and set(codes[:-1]) == {401} and len(codes) <= 6 and "retry-after" in low,
        str(codes),
    )


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    base, mailpit_url = argv[1], argv[2]
    origin = argv[3] if len(argv) > 3 else base.rstrip("/")
    try:
        run(base, mailpit_url, origin)
    except Exception as exc:  # report, then fail
        check("smoke test ran to completion", False, f"{type(exc).__name__}: {exc}")
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
