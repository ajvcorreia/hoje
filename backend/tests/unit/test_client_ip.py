"""client_ip: X-Real-IP (set by hoje-web) when trusted, never X-Forwarded-For."""

import pytest
from starlette.requests import Request

from hoje.api.deps import client_ip, throttle_ip
from hoje.config import get_settings

PEER = "172.18.0.5"


def make_request(headers: dict[str, str] | None = None, peer: str | None = PEER) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": (peer, 40000) if peer else None,
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOJE_DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
    monkeypatch.setenv("HOJE_SECRET_KEY", "Y2ktb25seS10aHJvd2F3YXkta2V5LTAwMDAwMDAwMDA=")
    monkeypatch.setenv("HOJE_ENV", "test")
    monkeypatch.delenv("HOJE_TRUST_REAL_IP_HEADER", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_uses_x_real_ip_by_default():
    assert client_ip(make_request({"X-Real-IP": "203.0.113.9"})) == "203.0.113.9"


def test_normalizes_ipv6():
    req = make_request({"X-Real-IP": "2001:DB8:0:0:0:0:0:1"})
    assert client_ip(req) == "2001:db8::1"


def test_ignores_x_forwarded_for_entirely():
    assert client_ip(make_request({"X-Forwarded-For": "1.2.3.4"})) == PEER
    both = make_request({"X-Forwarded-For": "1.2.3.4, 5.6.7.8", "X-Real-IP": "203.0.113.9"})
    assert client_ip(both) == "203.0.113.9"


@pytest.mark.parametrize("value", ["", "not-an-ip", "1.2.3.4, 5.6.7.8", "999.1.1.1", "1.2.3.4:80"])
def test_invalid_x_real_ip_falls_back_to_the_peer(value: str):
    assert client_ip(make_request({"X-Real-IP": value})) == PEER


def test_peer_when_header_missing():
    assert client_ip(make_request()) == PEER


def test_ignores_x_real_ip_when_not_trusted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOJE_TRUST_REAL_IP_HEADER", "false")
    get_settings.cache_clear()
    assert client_ip(make_request({"X-Real-IP": "203.0.113.9"})) == PEER


def test_throttle_ip_uses_the_resolved_address_or_unknown():
    assert throttle_ip(make_request({"X-Real-IP": "203.0.113.9"})) == "203.0.113.9"
    assert throttle_ip(make_request(peer=None)) == "unknown"
