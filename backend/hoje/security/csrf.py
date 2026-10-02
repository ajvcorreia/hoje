"""Origin checking for unsafe requests (the CSRF token itself lives in ``tokens``)."""

from urllib.parse import urlsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def origin_of(url: str | None) -> str | None:
    """Normalised ``scheme://host[:port]`` of a URL, or ``None`` if it has no usable origin."""
    if not url:
        return None
    try:
        parts = urlsplit(url.strip())
        scheme = parts.scheme.lower()
        host = parts.hostname
        port = parts.port
    except ValueError:
        return None
    if scheme not in _DEFAULT_PORTS or not host:
        return None
    host = f"[{host}]" if ":" in host else host
    if port is None or port == _DEFAULT_PORTS[scheme]:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def origin_allowed(origin: str | None, referer: str | None, public_url: str) -> bool:
    """True if the request's Origin (or, if absent, Referer) is the configured public origin."""
    expected = origin_of(public_url)
    if expected is None:
        return False
    if origin is not None:
        return origin_of(origin) == expected  # "null" and garbage never match
    if referer is not None:
        return origin_of(referer) == expected
    return False
