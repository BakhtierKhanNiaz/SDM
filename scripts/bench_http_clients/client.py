"""Throughput and CPU cost of httpx (sync + async) and aiohttp. Usage: client.py <port>"""

import asyncio
import inspect
import statistics
import sys
import threading
import time

import aiohttp
import aiohttp.http_parser
import httpx

PORT = int(sys.argv[1])
URL = f"http://127.0.0.1:{PORT}/file"
SIZE = 256 * 1024 * 1024
RUNS = 3
SEGMENTS = 8
CHUNK = 64 * 1024


def ranges():
    step = SIZE // SEGMENTS
    return [
        (i * step, SIZE - 1 if i == SEGMENTS - 1 else (i + 1) * step - 1) for i in range(SEGMENTS)
    ]


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def httpx_sync_1conn():
    total = 0
    with httpx.Client(timeout=30) as c, c.stream("GET", URL) as r:
        r.raise_for_status()
        for chunk in r.iter_bytes(CHUNK):
            total += len(chunk)
    return total


def httpx_sync_8seg():
    totals = []
    lock = threading.Lock()
    with httpx.Client(timeout=30, limits=httpx.Limits(max_connections=SEGMENTS)) as c:

        def worker(a, b):
            n = 0
            with c.stream("GET", URL, headers={"Range": f"bytes={a}-{b}"}) as r:
                expect(r.status_code == 206, f"expected 206, got {r.status_code}")
                for chunk in r.iter_bytes(CHUNK):
                    n += len(chunk)
            with lock:
                totals.append(n)

        threads = [threading.Thread(target=worker, args=rg) for rg in ranges()]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    return sum(totals)


async def httpx_async_1conn():
    total = 0
    async with httpx.AsyncClient(timeout=30) as c, c.stream("GET", URL) as r:
        r.raise_for_status()
        async for chunk in r.aiter_bytes(CHUNK):
            total += len(chunk)
    return total


async def httpx_async_8seg():
    async with httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_connections=SEGMENTS)) as c:

        async def seg(a, b):
            n = 0
            async with c.stream("GET", URL, headers={"Range": f"bytes={a}-{b}"}) as r:
                expect(r.status_code == 206, f"expected 206, got {r.status_code}")
                async for chunk in r.aiter_bytes(CHUNK):
                    n += len(chunk)
            return n

        return sum(await asyncio.gather(*(seg(a, b) for a, b in ranges())))


async def aiohttp_1conn():
    total = 0
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
        async with s.get(URL) as r:
            r.raise_for_status()
            async for chunk in r.content.iter_chunked(CHUNK):
                total += len(chunk)
    return total


async def aiohttp_8seg():
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:

        async def seg(a, b):
            n = 0
            async with s.get(URL, headers={"Range": f"bytes={a}-{b}"}) as r:
                expect(r.status == 206, f"expected 206, got {r.status}")
                async for chunk in r.content.iter_chunked(CHUNK):
                    n += len(chunk)
            return n

        return sum(await asyncio.gather(*(seg(a, b) for a, b in ranges())))


def measure(fn):
    walls, cpus = [], []
    for _ in range(RUNS):
        c0, w0 = time.process_time(), time.perf_counter()
        n = asyncio.run(fn()) if inspect.iscoroutinefunction(fn) else fn()
        walls.append(time.perf_counter() - w0)
        cpus.append(time.process_time() - c0)
        expect(n == SIZE, f"{fn.__name__} received {n} bytes, expected {SIZE}")
    w, c = statistics.median(walls), statistics.median(cpus)
    gb = SIZE / 1024**3
    print(
        f"{fn.__name__:18} {SIZE / 1024**2 / w:8.0f} MB/s   {c / gb:6.2f} CPU-s per GB   "
        f"(median of {RUNS}, wall {w:.2f}s)"
    )


print(
    f"httpx {httpx.__version__}, aiohttp {aiohttp.__version__}, "
    f"aiohttp parser: {aiohttp.http_parser.HttpResponseParser.__module__}"
)
print(f"Downloading {SIZE // 1024**2} MiB over loopback, chunk {CHUNK // 1024} KiB\n")
for fn in (
    httpx_sync_1conn,
    httpx_async_1conn,
    aiohttp_1conn,
    httpx_sync_8seg,
    httpx_async_8seg,
    aiohttp_8seg,
):
    measure(fn)
