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
