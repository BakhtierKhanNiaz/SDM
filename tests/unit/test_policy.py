"""Network policy: which addresses SDM may connect to."""

import asyncio
import socket

import pytest

from sdm.core.errors import BlockedDestinationError
from sdm.engine.policy import NetworkPolicy, PolicyResolver

DEFAULT = NetworkPolicy()


@pytest.mark.parametrize("ip", ["8.8.8.8", "93.184.215.14", "2606:4700:4700::1111"])
def test_public_addresses_are_allowed(ip):
    DEFAULT.check_ip(ip, "example.com")


@pytest.mark.parametrize("ip", ["127.0.0.1", "127.8.9.10", "::1", "::ffff:127.0.0.1"])
def test_this_computer_is_blocked_by_default(ip):
    with pytest.raises(BlockedDestinationError, match="this computer"):
        DEFAULT.check_ip(ip, "host")


def test_this_computer_is_allowed_only_when_enabled():
    NetworkPolicy(allow_loopback=True).check_ip("127.0.0.1", "host")


@pytest.mark.parametrize("ip", ["10.0.0.5", "172.16.3.4", "192.168.1.10", "100.64.0.1", "fd12::1"])
def test_private_networks_need_opt_in(ip):
    with pytest.raises(BlockedDestinationError, match="--allow-local-network"):
        DEFAULT.check_ip(ip, "nas")
    NetworkPolicy(allow_local_network=True).check_ip(ip, "nas")


@pytest.mark.parametrize(
    "ip", ["169.254.169.254", "fe80::1", "0.0.0.0", "::", "224.0.0.1", "ff02::1", "240.0.0.1"]
)
def test_special_addresses_are_always_blocked(ip):
    permissive = NetworkPolicy(allow_local_network=True, allow_loopback=True)
    with pytest.raises(BlockedDestinationError):
        permissive.check_ip(ip, "host")


def test_url_host_check_covers_ip_literals_only():
    DEFAULT.check_url_host("example.com")  # hostnames are checked after DNS lookup
    for literal in ("127.0.0.1", "::1", "10.1.2.3"):
        with pytest.raises(BlockedDestinationError):
            DEFAULT.check_url_host(literal)


def test_resolver_blocks_names_that_resolve_to_this_computer():
    async def resolve():
        return await PolicyResolver(DEFAULT).resolve("localhost", 80, socket.AF_UNSPEC)

    with pytest.raises(BlockedDestinationError, match="localhost points to this computer"):
        asyncio.run(resolve())


@pytest.mark.parametrize(
    ("ip", "leads_to"),
    [
        ("64:ff9b::7f00:1", "this computer"),  # NAT64 wrapping 127.0.0.1
        ("2002:7f00:1::", "this computer"),  # 6to4 wrapping 127.0.0.1
        ("64:ff9b::c0a8:101", "local or private"),  # NAT64 wrapping 192.168.1.1
        ("2002:c0a8:101::1", "local or private"),  # 6to4 wrapping 192.168.1.1
        ("64:ff9b::a9fe:a9fe", "special"),  # NAT64 wrapping 169.254.169.254
        ("2002:a9fe:a9fe::", "special"),  # 6to4 wrapping 169.254.169.254
    ],
)
def test_ipv4_hidden_inside_ipv6_is_checked_as_ipv4(ip, leads_to):
    # Known gap closed in M10: these used to be judged as IPv6 addresses.
    with pytest.raises(BlockedDestinationError, match=leads_to):
        NetworkPolicy().check_ip(ip, "example.test")


@pytest.mark.parametrize("ip", ["64:ff9b::808:808", "2002:808:808::1"])  # wrapping 8.8.8.8
def test_public_ipv4_inside_ipv6_is_allowed(ip):
    NetworkPolicy().check_ip(ip, "example.test")


def test_embedded_private_address_follows_the_local_network_option():
    NetworkPolicy(allow_local_network=True).check_ip("64:ff9b::c0a8:101", "nas.test")
