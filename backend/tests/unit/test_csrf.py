import hashlib

import pytest

from hoje.security.csrf import origin_allowed, origin_of
from hoje.security.tokens import constant_time_equals, csrf_token, hash_token

KEY = bytes(range(32))
PUBLIC = "https://hoje.example.com"


def test_csrf_token_is_deterministic_and_keyed() -> None:
    a = csrf_token(KEY, "secret-1")
    assert a == csrf_token(KEY, "secret-1")
    assert a != csrf_token(KEY, "secret-2")
    assert a != csrf_token(bytes(32), "secret-1")
    assert a != "secret-1"
    assert len(a) == 64


def test_constant_time_equals_handles_unicode() -> None:
    assert constant_time_equals("abc", "abc")
    assert not constant_time_equals("abc", "abd")
    assert not constant_time_equals("é", "e")


def test_hash_token_is_sha256_hex() -> None:
    assert hash_token("x") == hashlib.sha256(b"x").hexdigest()


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://Hoje.Example.com", "https://hoje.example.com"),
        ("https://hoje.example.com:443/path?q=1", "https://hoje.example.com"),
        ("http://localhost:8080/", "http://localhost:8080"),
        ("http://localhost:80", "http://localhost"),
        ("http://[::1]:8080/x", "http://[::1]:8080"),
        ("null", None),
        ("", None),
        (None, None),
        ("javascript:alert(1)", None),
        ("https://", None),
        ("https://host:notaport", None),
    ],
)
def test_origin_of(url: str | None, expected: str | None) -> None:
    assert origin_of(url) == expected


def test_matching_origin_allowed() -> None:
    assert origin_allowed(PUBLIC, None, PUBLIC)
    assert origin_allowed(PUBLIC, "https://evil.test/", PUBLIC)  # Origin wins over Referer


@pytest.mark.parametrize(
    "origin",
    ["https://evil.test", "http://hoje.example.com", "https://hoje.example.com:8443", "null", ""],
)
def test_other_origins_rejected(origin: str) -> None:
    # No fallback to Referer once an Origin header was sent.
    assert not origin_allowed(origin, PUBLIC + "/page", PUBLIC)


def test_referer_fallback_only_without_origin() -> None:
    assert origin_allowed(None, PUBLIC + "/settings?x=1", PUBLIC)
    assert not origin_allowed(None, "https://evil.test/", PUBLIC)
    assert not origin_allowed(None, "not a url", PUBLIC)


def test_both_missing_rejected() -> None:
    assert not origin_allowed(None, None, PUBLIC)
