"""Can each library (1) validate resolved IPs at connect time, including on redirect hops,
and (2) stop a stalled download promptly? Usage: hooks.py <port>

Demo policy: the literal 127.0.0.1 is allowed (it's the test server), but any *hostname*
that resolves to a loopback address is blocked. SDM's real policy is stricter.
"""

import asyncio
import inspect
import ipaddress
import socket
import sys
import threading
import time

import aiohttp
import httpcore
import httpx
from aiohttp.resolver import ThreadedResolver

PORT = int(sys.argv[1])
BASE = f"http://127.0.0.1:{PORT}"


def blocked(host: str, ip: str) -> bool:
    return host != "127.0.0.1" and ipaddress.ip_address(ip).is_loopback


# ---------- 1. connect-time IP validation ----------

print("== httpx: hook points ==")
params = list(inspect.signature(httpx.HTTPTransport.__init__).parameters)
print("HTTPTransport params:", params)
print("has network_backend param:", "network_backend" in params)


class ValidatingBackend(httpcore.SyncBackend):
    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        for info in infos:
            if blocked(host, info[4][0]):
                raise httpcore.ConnectError(f"blocked {host} -> {info[4][0]}")
        return super().connect_tcp(infos[0][4][0], port, timeout, local_address, socket_options)


transport = httpx.HTTPTransport()
transport._pool = httpcore.ConnectionPool(network_backend=ValidatingBackend())  # private attr
with httpx.Client(transport=transport, follow_redirects=True, timeout=5) as c:
    for path in ("/small", "/redirect"):
        try:
            r = c.get(BASE + path)
            print(f"httpx GET {path}: {r.status_code} {len(r.content)} bytes (final {r.url})")
        except Exception as e:
            print(f"httpx GET {path}: {type(e).__name__}: {e}")


print("\n== aiohttp: custom resolver ==")


class ValidatingResolver(ThreadedResolver):
    async def resolve(self, host, port=0, family=socket.AF_INET):
        infos = await super().resolve(host, port, family)
        for info in infos:
            if blocked(host, info["host"]):
                raise OSError(f"blocked {host} -> {info['host']}")
        return infos


async def aiohttp_hooks():
    conn = aiohttp.TCPConnector(resolver=ValidatingResolver())
    async with aiohttp.ClientSession(connector=conn, timeout=aiohttp.ClientTimeout(total=5)) as s:
        for url in (BASE + "/small", BASE + "/redirect", f"http://localhost:{PORT}/small"):
            shown = url[len("http://") :]
            try:
                async with s.get(url) as r:
                    body = await r.read()
                    print(f"aiohttp GET {shown}: {r.status} {len(body)} bytes (final {r.url})")
            except Exception as e:
                print(f"aiohttp GET {shown}: {type(e).__name__}: {e}")


asyncio.run(aiohttp_hooks())


# ---------- 2. cancelling a stalled download ----------

print("\n== cancel a download whose server has gone silent (read timeout 10 s) ==")


def httpx_sync_cancel():
    state = {}

    def worker():
        try:
            with httpx.Client(timeout=10) as c, c.stream("GET", BASE + "/stall") as r:
                state["resp"] = r
                for _ in r.iter_bytes():
                    pass
        except Exception as e:
            state["error"] = type(e).__name__

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.5)
    t0 = time.perf_counter()
    state["resp"].close()  # closing from another thread: the only lever a sync client offers
    t.join()
    print(
        f"httpx sync (close from other thread): stopped after {time.perf_counter() - t0:.2f}s"
        f" [{state.get('error', 'no error')}]"
    )


async def async_cancel(name, reader):
    task = asyncio.create_task(reader())
    await asyncio.sleep(0.5)
    t0 = time.perf_counter()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    print(f"{name} (task.cancel()): stopped after {time.perf_counter() - t0:.3f}s")


async def httpx_async_reader():
    async with httpx.AsyncClient(timeout=10) as c, c.stream("GET", BASE + "/stall") as r:
        async for _ in r.aiter_bytes():
            pass


async def aiohttp_reader():
    async with aiohttp.ClientSession() as s, s.get(BASE + "/stall") as r:
        async for _ in r.content.iter_chunked(65536):
            pass


httpx_sync_cancel()
asyncio.run(async_cancel("httpx async", httpx_async_reader))
asyncio.run(async_cancel("aiohttp", aiohttp_reader))
