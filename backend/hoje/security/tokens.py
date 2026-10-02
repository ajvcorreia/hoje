"""Opaque tokens, CSRF derivation and recovery codes."""

import hashlib
import hmac
import re
import secrets

RECOVERY_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"  # RFC 4648 base32
RECOVERY_CODE_LENGTH = 10
RECOVERY_CODE_COUNT = 10
_RECOVERY_RE = re.compile(r"^[A-Z2-7]{10}$")
_STRIP_RE = re.compile(r"[\s\-]")


def new_token() -> str:
    """A 256-bit URL-safe random token."""
    return secrets.token_urlsafe(32)


def hash_token(raw: str) -> str:
    """sha256 hex digest: what the database stores instead of the token."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def email_key(email: str) -> str:
    """Stable, non-reversible throttle key part for an email address."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def csrf_token(secret_key: bytes, csrf_secret: str) -> str:
    """The token handed to the client: HMAC of the per-session secret under the server key."""
    return hmac.new(secret_key, csrf_secret.encode("utf-8"), hashlib.sha256).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """``count`` distinct codes formatted ``xxxxx-xxxxx`` (upper-case base32)."""
    codes: list[str] = []
    while len(codes) < count:
        raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(RECOVERY_CODE_LENGTH))
        code = f"{raw[:5]}-{raw[5:]}"
        if code not in codes:
            codes.append(code)
    return codes


def normalize_recovery_code(code: str) -> str | None:
    """Canonical form (10 upper-case chars) or ``None`` if ``code`` is not a recovery code."""
    candidate = _STRIP_RE.sub("", code).upper()
    return candidate if _RECOVERY_RE.match(candidate) else None
