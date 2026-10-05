"""Server-side request forgery guard for user-supplied integration URLs (FelizAnniv).

The server fetches a URL that a signed-in user typed, from inside the Docker networks that also
hold the database and the API. Every outbound request therefore goes through three steps:

1. ``parse_base_url``: http/https only, no userinfo, query or fragment, a sane length, a real
   port (never 0) and a host name that is either a DNS name or a canonical IP literal (decimal,
   octal and hex forms such as ``2130706433`` or ``0x7f.1`` are refused outright).
2. ``resolve_and_check``: resolve the name once and refuse if ANY resulting address is not
   allowed by the ``AddressPolicy`` (below).
3. The caller connects to the vetted address itself (``Target.ip``), sending the original host
   in the ``Host`` header and as the TLS server name, so a DNS answer that changes between the
   check and the connection (DNS rebinding) cannot redirect the request. Redirects are never
   followed.

Address policy:

* always refused: loopback, link-local (incl. 169.254.169.254 and fe80::/10), unspecified,
  multicast, reserved, site-local and broadcast addresses, also when they are embedded in an
  IPv6 address (IPv4-mapped ``::ffff:127.0.0.1``, IPv4-compatible, 6to4, Teredo, NAT64);
* other non-global addresses (10/8, 172.16/12, 192.168/16, 100.64/10, fc00::/7, documentation
  and benchmarking ranges) only inside ``HOJE_INTEGRATION_ALLOWED_PRIVATE_CIDRS``;
* addresses inside the networks this container is attached to (the Docker networks that hold
  ``db``, ``api`` and ``hoje-web``) only when an allowed CIDR containing the address is strictly
  narrower than that network, normally the exact ``/32`` of a FelizAnniv container that shares
  a network with Hoje. Allowing a whole range (for example ``172.16.0.0/12``) never opens the
  database or the web container.
"""

import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
Resolver = Callable[[str, int], Awaitable[list[str]]]

MAX_URL_LENGTH = 2048
NOT_ALLOWED = "That address is not allowed"
PRIVATE_HINT = (
    "That address is in a private network. The server administrator can allow it with "
    "HOJE_INTEGRATION_ALLOWED_PRIVATE_CIDRS."
)
OWN_NETWORK_HINT = (
    "That address is inside Hoje's own container network. The server administrator can allow "
    "one exact address there (for example 172.18.0.5/32) with "
    "HOJE_INTEGRATION_ALLOWED_PRIVATE_CIDRS."
)

_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_THIS_NETWORK = ipaddress.ip_network("0.0.0.0/8")
_HOST_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
# Anything that only uses characters of numeric IPv4 notations (digits, dots, x for hex).
_NUMERIC_LIKE = re.compile(r"^(0x[0-9a-f]*|[0-9]+)(\.(0x[0-9a-f]*|[0-9]*))*$")


class InvalidUrl(ValueError):
    """The URL is malformed or uses something we do not support. The message is user-safe."""


class DisallowedAddress(Exception):
    """The destination is not allowed by the policy. The message is user-safe."""


class ResolutionError(Exception):
    """The host name does not resolve. The message is user-safe."""


@dataclass(frozen=True, slots=True)
class BaseUrl:
    """A validated integration base URL (no trailing slash)."""

    scheme: str
    host: str  # lower-case ASCII (IDNA) host name or IP literal, without brackets
    port: int
    path: str  # "" or "/prefix" without a trailing slash

    @property
    def default_port(self) -> bool:
        return self.port == (443 if self.scheme == "https" else 80)

    @property
    def host_header(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return host if self.default_port else f"{host}:{self.port}"

    def __str__(self) -> str:
        return f"{self.scheme}://{self.host_header}{self.path}"


@dataclass(frozen=True, slots=True)
class Target:
    """Where to connect: the vetted ``ip`` for ``url.host``."""

    url: BaseUrl
    ip: str

    def request_url(self, path: str, query: str = "") -> str:
        ip = f"[{self.ip}]" if ":" in self.ip else self.ip
        netloc = ip if self.url.default_port else f"{ip}:{self.url.port}"
        return f"{self.url.scheme}://{netloc}{self.url.path}{path}{'?' + query if query else ''}"

    @property
    def tls_server_name(self) -> str | None:
        """The name the TLS certificate must match (``None`` for http or an IP literal)."""
        if self.url.scheme != "https" or _ip_literal(self.url.host) is not None:
            return None
        return self.url.host


# --------------------------------------------------------------------------- URL parsing


def _ip_literal(host: str) -> IPAddress | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _normalise_host(raw: str) -> str:
    host = raw.strip().lower().rstrip(".")
    if not host:
        raise InvalidUrl("Enter an address such as https://felizanniv.example.com")
    if _ip_literal(host) is not None:
        return host
    if _NUMERIC_LIKE.match(host):
        # 2130706433, 0177.0.0.1, 0x7f.1, 127.1: all valid to inet_aton, all refused here.
        raise InvalidUrl(f"{NOT_ALLOWED}: write IP addresses in the usual dotted form")
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise InvalidUrl("The host name is not valid") from exc
    labels = ascii_host.split(".")
    if len(ascii_host) > 253 or not all(_HOST_LABEL.match(label) for label in labels):
        raise InvalidUrl("The host name is not valid")
    return ascii_host


def parse_base_url(raw: str) -> BaseUrl:
    """Validate the FelizAnniv address a user typed. Raises ``InvalidUrl``."""
    value = raw.strip()
    if not value:
        raise InvalidUrl("Enter the address of your FelizAnniv server")
    if len(value) > MAX_URL_LENGTH:
        raise InvalidUrl("The address is too long")
    if any(ord(c) < 0x21 or ord(c) == 0x7F or c == "\\" for c in value):
        raise InvalidUrl("The address contains spaces or control characters")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise InvalidUrl("The address is not a valid URL") from exc
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise InvalidUrl("The address must start with http:// or https://")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise InvalidUrl("The address must not contain a user name or password")
    if parts.query or parts.fragment or "?" in value or "#" in value:
        raise InvalidUrl("The address must not contain a query (?) or fragment (#)")
    if parts.hostname is None:
        raise InvalidUrl("Enter an address such as https://felizanniv.example.com")
    if port == 0:
        raise InvalidUrl(f"{NOT_ALLOWED}: port 0")
    host = _normalise_host(parts.hostname)
    path = parts.path.rstrip("/")
    if any(segment in (".", "..") for segment in path.split("/")):
        raise InvalidUrl("The address must not contain . or .. path segments")
    return BaseUrl(
        scheme=scheme, host=host, port=port or (443 if scheme == "https" else 80), path=path
    )


# --------------------------------------------------------------------------- policy


def _embedded_ipv4(ip: ipaddress.IPv6Address) -> list[ipaddress.IPv4Address]:
    found = []
    if ip.sixtofour is not None:
        found.append(ip.sixtofour)
    if ip.teredo is not None:
        found.extend(ip.teredo)
    if ip in _NAT64:
        found.append(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
    packed = ip.packed
    if packed[:12] == bytes(12) and int(ip) > 1:  # deprecated IPv4-compatible ::a.b.c.d
        found.append(ipaddress.IPv4Address(packed[12:]))
    return found


def _always_blocked(ip: IPAddress) -> bool:
    if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        return True
    if isinstance(ip, ipaddress.IPv4Address):
        return ip in _THIS_NETWORK or ip == ipaddress.IPv4Address("255.255.255.255")
    return ip.is_site_local


class AddressPolicy:
    def __init__(
        self, allowed_private: Sequence[IPNetwork], own_networks: Sequence[IPNetwork] = ()
    ) -> None:
        self.allowed_private = list(allowed_private)
        self.own_networks = list(own_networks)

    def check(self, ip: IPAddress) -> None:
        """Raise ``DisallowedAddress`` unless a connection to ``ip`` is allowed."""
        candidates: list[IPAddress] = [ip]
        if isinstance(ip, ipaddress.IPv6Address):
            if ip.ipv4_mapped is not None:
                candidates = [ip.ipv4_mapped]  # ::ffff:a.b.c.d is a.b.c.d on the wire
            else:
                candidates.extend(_embedded_ipv4(ip))
        for candidate in candidates:
            if _always_blocked(candidate):
                raise DisallowedAddress(NOT_ALLOWED)
        for candidate in candidates:
            self._check_ranges(candidate)

    def _check_ranges(self, ip: IPAddress) -> None:
        allowing = [n for n in self.allowed_private if n.version == ip.version and ip in n]
        for own in self.own_networks:
            if own.version == ip.version and ip in own:
                narrower = [
                    n
                    for n in allowing
                    if n.prefixlen > own.prefixlen and n.subnet_of(own)  # type: ignore[arg-type]
                ]
                if not narrower:
                    raise DisallowedAddress(OWN_NETWORK_HINT)
                return
        if not ip.is_global and not allowing:
            raise DisallowedAddress(PRIVATE_HINT)


# --------------------------------------------------------------------------- own networks


def _proc_ipv4(value: int) -> ipaddress.IPv4Address:
    """/proc/net/route prints addresses as native-endian integers of network-order bytes."""
    return ipaddress.IPv4Address(socket.ntohl(value))


def _proc_networks(route: Path, if_inet6: Path) -> list[IPNetwork]:
    """Directly connected networks of this host/container, read from /proc (Linux only)."""
    networks: list[IPNetwork] = []
    try:
        for line in route.read_text().splitlines()[1:]:
            fields = line.split()
            if len(fields) < 8 or fields[0] == "lo":
                continue
            dest, gateway, mask = (int(fields[i], 16) for i in (1, 2, 7))
            if gateway != 0 or mask == 0:
                continue  # routed or default: not a network we sit on
            networks.append(
                ipaddress.ip_network(f"{_proc_ipv4(dest)}/{_proc_ipv4(mask)}", strict=False)
            )
    except OSError:
        pass
    try:
        for line in if_inet6.read_text().splitlines():
            fields = line.split()
            if len(fields) < 6 or fields[5] == "lo":
                continue
            addr = ipaddress.IPv6Address(int(fields[0], 16))
            if addr.is_link_local or addr.is_loopback:
                continue  # always blocked anyway
            networks.append(ipaddress.ip_network(f"{addr}/{int(fields[2], 16)}", strict=False))
    except (OSError, ValueError):
        pass
    return sorted(set(networks), key=lambda n: (n.version, str(n)))


@lru_cache
def own_networks() -> tuple[IPNetwork, ...]:
    """The networks this process's container is attached to (computed once)."""
    return tuple(_proc_networks(Path("/proc/net/route"), Path("/proc/net/if_inet6")))


def default_policy(allowed_private: Iterable[IPNetwork]) -> AddressPolicy:
    return AddressPolicy(list(allowed_private), own_networks())


# --------------------------------------------------------------------------- resolution


async def system_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


async def resolve_and_check(
    url: BaseUrl, policy: AddressPolicy, resolver: Resolver = system_resolver
) -> Target:
    """Resolve ``url.host`` once, vet every address and pin the first one."""
    literal = _ip_literal(url.host)
    if literal is not None:
        addresses = [literal]
    else:
        try:
            raw = await resolver(url.host, url.port)
        except (OSError, UnicodeError) as exc:
            raise ResolutionError(f"Could not resolve the host name {url.host}") from exc
        addresses = []
        for value in raw:
            try:
                addresses.append(ipaddress.ip_address(value.split("%", 1)[0]))
            except ValueError as exc:
                raise DisallowedAddress(NOT_ALLOWED) from exc
        if not addresses:
            raise ResolutionError(f"Could not resolve the host name {url.host}")
    for address in addresses:
        policy.check(address)
    return Target(url=url, ip=str(addresses[0]))
