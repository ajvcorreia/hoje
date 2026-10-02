from datetime import UTC, datetime

import pyotp

from hoje.security import totp

SECRET = "JBSWY3DPEHPK3PXP"  # noqa: S105
T0 = datetime(2026, 5, 1, 12, 0, 10, tzinfo=UTC)


def _code(at: datetime, offset_steps: int = 0) -> str:
    return pyotp.TOTP(SECRET).at(int(at.timestamp()) + offset_steps * 30)


def test_current_code_accepted_and_returns_step() -> None:
    assert totp.verify(SECRET, _code(T0), now=T0, last_step=None) == totp.current_step(T0)


def test_window_accepts_one_step_either_side() -> None:
    step = totp.current_step(T0)
    assert totp.verify(SECRET, _code(T0, -1), now=T0, last_step=None) == step - 1
    assert totp.verify(SECRET, _code(T0, 1), now=T0, last_step=None) == step + 1


def test_outside_window_rejected() -> None:
    assert totp.verify(SECRET, _code(T0, -2), now=T0, last_step=None) is None
    assert totp.verify(SECRET, _code(T0, 2), now=T0, last_step=None) is None


def test_replay_of_same_step_rejected() -> None:
    step = totp.verify(SECRET, _code(T0), now=T0, last_step=None)
    assert step is not None
    assert totp.verify(SECRET, _code(T0), now=T0, last_step=step) is None


def test_older_step_rejected_after_newer_accepted() -> None:
    newer = totp.verify(SECRET, _code(T0, 1), now=T0, last_step=None)
    assert newer is not None
    assert totp.verify(SECRET, _code(T0, -1), now=T0, last_step=newer) is None


def test_next_step_accepted_after_previous() -> None:
    step = totp.current_step(T0)
    later = datetime.fromtimestamp((step + 1) * 30 + 1, UTC)
    assert totp.verify(SECRET, _code(later), now=later, last_step=step) == step + 1


def test_malformed_codes_rejected() -> None:
    for bad in ("", "12345", "1234567", "abcdef", "12345a", "١٢٣٤٥٦"):
        assert totp.verify(SECRET, bad, now=T0, last_step=None) is None


def test_provisioning_uri_and_qr() -> None:
    uri = totp.provisioning_uri(SECRET, "ana@example.com")
    assert uri.startswith("otpauth://totp/Hoje:ana%40example.com?")
    assert "issuer=Hoje" in uri
    svg = totp.qr_svg(uri)
    assert svg.startswith("<svg")
    assert "<?xml" not in svg
    assert "<script" not in svg
