"""Local test server for the HTTP client evaluation. Usage: server.py <file> <port>

/file      a 256 MiB synthetic file (Range requests supported, served with sendfile)
/small     1 KiB body
/redirect  302 to http://localhost:<port>/small (a hostname that resolves to loopback)
/stall     sends 1 KiB of a 10 MB body, then goes silent for 30 s
"""

import asyncio
import os
import sys

from aiohttp import web

FILE, PORT = sys.argv[1], int(sys.argv[2])
SIZE = 256 * 1024 * 1024

if not os.path.exists(FILE) or os.path.getsize(FILE) != SIZE:
    with open(FILE, "wb") as f:
        for _ in range(SIZE // (4 * 1024 * 1024)):
            f.write(os.urandom(4 * 1024 * 1024))


async def file_handler(request):
    return web.FileResponse(FILE)


async def small_handler(request):
    return web.Response(body=b"x" * 1024)


async def redirect_handler(request):
    raise web.HTTPFound(f"http://localhost:{PORT}/small")


async def stall_handler(request):
    resp = web.StreamResponse()
    resp.content_length = 10_000_000
    await resp.prepare(request)
    await resp.write(b"x" * 1024)
    await asyncio.sleep(30)
    return resp


app = web.Application()
app.add_routes(
    [
        web.get("/file", file_handler),
        web.get("/small", small_handler),
        web.get("/redirect", redirect_handler),
        web.get("/stall", stall_handler),
    ]
)
web.run_app(app, host="127.0.0.1", port=PORT, print=None, access_log=None)
