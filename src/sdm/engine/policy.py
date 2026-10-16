"""Network policy: which IP addresses SDM may connect to.

This defends against server-side request forgery (SSRF): a link, redirect or DNS answer that
points SDM at this computer, the router, or another device on the local network. Addresses
are checked twice:

1. IP literals in a URL (http://10.0.0.1/...) are checked before each request, including
   every redirect hop.
2. Hostnames are checked after DNS resolution, inside aiohttp's resolver, so the addresses
   that get checked are exactly the ones aiohttp connects to. That also covers DNS tricks
   such as a name that resolves to a public address once and to 127.0.0.1 later.
"""

import ipaddress
import socket
from dataclasses import dataclass

from aiohttp.abc import ResolveResult
from aiohttp.resolver import ThreadedResolver

from sdm.core.errors import BlockedDestinationError


@dataclass(frozen=True)
class NetworkPolicy:
    """Rules for destination addresses.

    allow_local_network: private LAN ranges such as 192.168.x.x (a NAS, for example).
    allow_loopback: this computer (127.0.0.1, ::1). Only tests turn this on.
    Link-local (including 169.254.169.254), multicast, unspecified and reserved addresses
    are always blocked.
    """

    allow_local_network: bool = False
    allow_loopback: bool = False

    def check_ip(self, ip: str, host: str) -> None:
        """Raise BlockedDestinationError if `host`, which resolved to `ip`, is not allowed."""
        addr = ipaddress.ip_address(ip.split("%", 1)[0])  # drop an IPv6 zone such as %eth0
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
            addr = addr.ipv4_mapped  # ::ffff:127.0.0.1 is really 127.0.0.1

        if addr.is_loopback:
            if self.allow_loopback:
                return
            raise BlockedDestinationError(
                f"{host} points to this computer ({addr}); SDM does not download from it."
            )
        if addr.is_link_local or addr.is_multicast or addr.is_unspecified or addr.is_reserved:
            raise BlockedDestinationError(
                f"{host} points to a special network address ({addr}); SDM does not download "
                "from it."
            )
        if not addr.is_global:
            if self.allow_local_network:
                return
            raise BlockedDestinationError(
                f"{host} is on a local or private network ({addr}). "
                "Use --allow-local-network if you trust this server."
            )

    def check_url_host(self, host: str) -> None:
        """Check a URL's host if it is an IP literal; hostnames are checked after DNS lookup."""
        try:
            ipaddress.ip_address(host.split("%", 1)[0])
        except ValueError:
            return  # a hostname: PolicyResolver checks it once DNS has answered
        self.check_ip(host, host)


class PolicyResolver(ThreadedResolver):
    """aiohttp resolver that refuses hosts resolving to any address the policy blocks."""

    def __init__(self, policy: NetworkPolicy) -> None:
        super().__init__()
        self._policy = policy

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        results = await super().resolve(host, port, family)
        for result in results:
            self._policy.check_ip(result["host"], host)
        return results
