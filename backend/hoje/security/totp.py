"""TOTP (RFC 6238; SHA-1, 6 digits, 30 s) with a +-1 step window and replay protection."""

import hmac
import io
from datetime import datetime

import pyotp
import segno

STEP_SECONDS = 30
DIGITS = 6
WINDOW = 1
ISSUER = "Hoje"


def generate_secret() -> str:
    return pyotp.random_base32()


def current_step(now: datetime) -> int:
    return int(now.timestamp()) // STEP_SECONDS


def is_totp_format(code: str) -> bool:
    return len(code) == DIGITS and code.isascii() and code.isdigit()


def verify(secret: str, code: str, *, now: datetime, last_step: int | None) -> int | None:
    """Return the accepted time step, or ``None``.

    A code is only accepted for a step strictly greater than ``last_step`` (the last accepted
    one), so a code can never be used twice, nor can an older code be replayed.
    """
    if not is_totp_format(code):
        return None
    totp = pyotp.TOTP(secret, digits=DIGITS, interval=STEP_SECONDS)
    centre = current_step(now)
    matched: int | None = None
    for step in range(centre - WINDOW, centre + WINDOW + 1):
        # Evaluate every step so timing does not depend on which one matched.
        if hmac.compare_digest(totp.at(step * STEP_SECONDS), code):
            matched = step
    if matched is None or (last_step is not None and matched <= last_step):
        return None
    return matched


def provisioning_uri(secret: str, account: str) -> str:
    return pyotp.TOTP(secret, digits=DIGITS, interval=STEP_SECONDS).provisioning_uri(
        name=account, issuer_name=ISSUER
    )


def qr_svg(uri: str) -> str:
    """Render ``uri`` as a standalone SVG document (no XML declaration) for an ``<img>`` tag."""
    buffer = io.BytesIO()
    segno.make(uri, error="m").save(
        buffer,
        kind="svg",
        scale=5,
        border=2,
        dark="#000",
        light="#fff",
        xmldecl=False,
        svgns=True,
        nl=False,
    )
    return buffer.getvalue().decode("utf-8")
