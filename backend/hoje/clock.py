"""Single time source. Everything that needs "now" calls ``clock.now()`` so tests can patch it."""

from datetime import UTC, datetime


def now() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)
