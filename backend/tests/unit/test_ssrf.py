"""SSRF guard for user-supplied integration URLs (no network, no database)."""

import ipaddress
from pathlib import Path

import pytest

from hoje.config import parse_cidrs
from hoje.security import ssrf
from hoje.security.ssrf import AddressPolicy, DisallowedAddress, InvalidUrl, parse_base_url

ip = ipaddress.ip_address
net = ipaddress.ip_network

OWN = [net("172.18.0.0/16"), net("172.19.0.0/16")]


def policy(allowed: str = "", own=OWN) -> AddressPolicy:
    return AddressPolicy(parse_cidrs(allowed), own)


# --------------------------------------------------------------------------- URL parsing


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://felizanniv.example.com", "https://felizanniv.example.com"),
        ("https://FelizAnniv.Example.com/", "https://felizanniv.example.com"),
        ("http://192.168.10.5:4000", "http://192.168.10.5:4000"),
        ("http://192.168.10.5:80/", "http://192.168.10.5"),
        ("https://example.com:443/fa/", "https://example.com/fa"),
        ("http://[2001:db8::1]:4000", "http://[2001:db8::1]:4000"),
        ("  https://example.com  ", "https://example.com"),
    ],
)
def test_valid_urls_are_normalised(raw, expected):
    assert str(parse_base_url(raw)) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "felizanniv.example.com",
        "ftp://example.com",
        "file:///etc/passwd",
        "gopher://example.com",
        "https://user:pass@example.com",
        "https://user@example.com",
        "https://example.com/?x=1",
        "https://example.com/#frag",
        "https://example.com:0",
        "https://example.com:99999",
        "https://exa mple.com",
        "https://example.com/a b",
        "https://example.com\\@evil.com",
        "https://example.com/../admin",
        "https://-bad-.example.com",
        "https://" + "a" * 2100 + ".com",
        "http://",
    ],
)
def test_invalid_urls_are_refused(raw):
    with pytest.raises(InvalidUrl):
        parse_base_url(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "http://2130706433/",  # decimal 127.0.0.1
        "http://0177.0.0.1/",  # octal
        "http://0x7f.0.0.1/",  # hex
        "http://0x7f000001/",
        "http://127.1/",  # short form
        "http://017700000001/",
    ],
)
def test_non_canonical_numeric_hosts_are_refused(raw):
    with pytest.raises(InvalidUrl, match="not allowed"):
        parse_base_url(raw)


def test_target_pins_the_ip_but_keeps_the_host_name():
    url = parse_base_url("https://felizanniv.example.com:8443/base")
    target = ssrf.Target(url=url, ip="203.0.113.7")
    assert target.request_url("/api/v1/people", "page=1") == (
        "https://203.0.113.7:8443/base/api/v1/people?page=1"
    )
    assert url.host_header == "felizanniv.example.com:8443"
    assert target.tls_server_name == "felizanniv.example.com"
    v6 = ssrf.Target(url=parse_base_url("http://h.example.com"), ip="2001:db8::5")
    assert v6.request_url("/x") == "http://[2001:db8::5]/x"
    assert v6.tls_server_name is None


# --------------------------------------------------------------------------- address policy


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "127.8.9.10",
        "::1",
        "0.0.0.0",  # noqa: S104
        "::",
        "169.254.169.254",  # cloud metadata
        "169.254.1.1",
        "fe80::1",
        "224.0.0.1",
        "ff02::1",
        "240.0.0.1",
        "255.255.255.255",
        "0.1.2.3",
        "::ffff:127.0.0.1",  # IPv4-mapped loopback
        "::ffff:169.254.169.254",
        "::127.0.0.1",  # IPv4-compatible
        "2002:7f00:0001::",  # 6to4 of 127.0.0.1
        "64:ff9b::7f00:1",  # NAT64 of 127.0.0.1
        "fec0::1",  # site-local
    ],
)
def test_always_blocked_even_when_allowlisted(address):
    allow_everything = "0.0.0.0/0, ::/0, 127.0.0.0/8, 169.254.0.0/16, fe80::/10"
    with pytest.raises(DisallowedAddress):
        policy(allow_everything).check(ip(address))


@pytest.mark.parametrize(
    "address",
    ["10.0.0.5", "192.168.10.20", "172.16.3.4", "100.64.1.1", "fd00::5", "::ffff:192.168.10.20"],
)
def test_private_addresses_are_blocked_by_default(address):
    with pytest.raises(DisallowedAddress, match="HOJE_INTEGRATION_ALLOWED_PRIVATE_CIDRS"):
        policy().check(ip(address))


def test_private_addresses_inside_the_allowed_cidrs_pass():
    p = policy("192.168.10.0/24, fd00::/8")
    p.check(ip("192.168.10.20"))
    p.check(ip("::ffff:192.168.10.20"))
    p.check(ip("fd00::5"))
    with pytest.raises(DisallowedAddress):
        p.check(ip("192.168.11.20"))


def test_public_addresses_pass():
    policy().check(ip("93.184.216.34"))
    policy().check(ip("2606:4700:4700::1111"))


def test_own_container_networks_are_blocked_even_inside_a_wide_allowlist():
    p = policy("172.16.0.0/12")
    p.check(ip("172.20.0.9"))  # a private network Hoje is not on: allowed by the CIDR
    with pytest.raises(DisallowedAddress, match="own container network"):
        p.check(ip("172.18.0.2"))  # e.g. db
    with pytest.raises(DisallowedAddress, match="own container network"):
        policy("172.18.0.0/16").check(ip("172.18.0.2"))  # the whole network is not enough


def test_one_exact_address_in_an_own_network_can_be_allowed():
    p = policy("172.18.0.5/32")
    p.check(ip("172.18.0.5"))
    with pytest.raises(DisallowedAddress):
        p.check(ip("172.18.0.2"))


def test_own_network_rule_also_applies_to_public_ranges():
    p = AddressPolicy([], [net("93.184.216.0/24")])  # host networking on a public subnet
    with pytest.raises(DisallowedAddress):
        p.check(ip("93.184.216.9"))
    p.check(ip("93.184.217.9"))


def test_bad_cidr_setting_is_rejected():
    with pytest.raises(ValueError, match="not an IP network"):
        parse_cidrs("192.168.10.0/24, nonsense")
    assert parse_cidrs(" 10.0.0.1 ; 192.168.0.0/16 ") == [net("10.0.0.1/32"), net("192.168.0.0/16")]


# --------------------------------------------------------------------------- resolution


def fake_resolver(*answers: str):
    calls = []

    async def resolve(host: str, port: int) -> list[str]:
        calls.append((host, port))
        return list(answers)

    resolve.calls = calls  # type: ignore[attr-defined]
    return resolve


async def test_resolution_pins_the_first_vetted_address():
    resolver = fake_resolver("93.184.216.34", "93.184.216.35")
    target = await ssrf.resolve_and_check(
        parse_base_url("https://fa.example.com"), policy(), resolver
    )
    assert target.ip == "93.184.216.34"
    assert resolver.calls == [("fa.example.com", 443)]  # type: ignore[attr-defined]


async def test_any_bad_answer_rejects_the_whole_name():
    resolver = fake_resolver("93.184.216.34", "127.0.0.1")  # rebinding-style mixed answer
    with pytest.raises(DisallowedAddress):
        await ssrf.resolve_and_check(parse_base_url("http://fa.example.com"), policy(), resolver)


async def test_names_resolving_to_metadata_or_private_are_refused():
    for answer in ("169.254.169.254", "10.1.2.3", "::ffff:127.0.0.1"):
        with pytest.raises(DisallowedAddress):
            await ssrf.resolve_and_check(
                parse_base_url("http://fa.example.com"), policy(), fake_resolver(answer)
            )


async def test_ip_literals_skip_dns_but_not_the_policy():
    resolver = fake_resolver("93.184.216.34")
    with pytest.raises(DisallowedAddress):
        await ssrf.resolve_and_check(parse_base_url("http://[::1]:4000"), policy(), resolver)
    with pytest.raises(DisallowedAddress):
        await ssrf.resolve_and_check(parse_base_url("http://127.0.0.1"), policy(), resolver)
    target = await ssrf.resolve_and_check(
        parse_base_url("http://192.168.10.5:4000"), policy("192.168.10.0/24"), resolver
    )
    assert target.ip == "192.168.10.5"
    assert resolver.calls == []  # type: ignore[attr-defined]


async def test_unresolvable_names_fail_cleanly():
    async def broken(host: str, port: int) -> list[str]:
        raise OSError("Name or service not known")

    with pytest.raises(ssrf.ResolutionError, match="Could not resolve"):
        await ssrf.resolve_and_check(parse_base_url("http://nope.invalid"), policy(), broken)
    with pytest.raises(ssrf.ResolutionError):
        await ssrf.resolve_and_check(
            parse_base_url("http://empty.example"), policy(), fake_resolver()
        )


# --------------------------------------------------------------------------- own networks


def test_own_networks_are_read_from_proc(tmp_path: Path):
    route = tmp_path / "route"
    route.write_text(
        "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\tMTU\tWindow\tIRTT\n"
        "eth0\t00000000\t010012AC\t0003\t0\t0\t0\t00000000\t0\t0\t0\n"  # default route
        "eth0\t000012AC\t00000000\t0001\t0\t0\t0\t0000FFFF\t0\t0\t0\n"  # 172.18.0.0/16
        "eth1\t0014A8C0\t00000000\t0001\t0\t0\t0\t00FFFFFF\t0\t0\t0\n"  # 192.168.20.0/24
        "lo\t0000007F\t00000000\t0001\t0\t0\t0\t000000FF\t0\t0\t0\n"
    )
    inet6 = tmp_path / "if_inet6"
    inet6.write_text(
        "fd000000000000000000000000000005 05 40 00 80 eth0\n"
        "fe800000000000000000000000000001 05 40 20 80 eth0\n"
        "00000000000000000000000000000001 01 80 10 80 lo\n"
    )
    found = ssrf._proc_networks(route, inet6)
    assert set(found) == {net("172.18.0.0/16"), net("192.168.20.0/24"), net("fd00::/64")}
    assert ssrf._proc_networks(tmp_path / "missing", tmp_path / "missing6") == []
