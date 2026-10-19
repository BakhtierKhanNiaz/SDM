"""What the browser said about a link reaches the server and the file name (M8).

Two MockServers on different ports are two different sites (origins), so the "other site"
rules can be tested without the internet.
"""

import asyncio
import os

import pytest

from sdm.core.downloads import BrowserContext
from sdm.core.errors import DownloadError
from sdm.engine import http_download
from sdm.engine.models import DownloadSettings
from sdm.engine.policy import NetworkPolicy

DATA = os.urandom(50_000)


def referers(server) -> list[str | None]:
    return [headers.get("Referer") for headers in server.requests]


def test_same_site_page_is_sent_in_full(mock_server, fetch):
    mock_server.add("/a.zip", mock_server.file(DATA))
    page = mock_server.url("/downloads.html?list=2#top")
    fetch(mock_server.url("/a.zip"), context=BrowserContext(referrer=page))
    assert referers(mock_server) == [mock_server.url("/downloads.html?list=2")]


def test_another_server_gets_only_the_origin(mock_server, other_server, fetch):
    mock_server.add("/a.zip", mock_server.file(DATA))
    page = other_server.url("/private/page.html?token=s3cret")
    fetch(mock_server.url("/a.zip"), context=BrowserContext(referrer=page))
    assert referers(mock_server) == [other_server.url("/")]


def test_a_secure_page_is_never_sent_to_an_insecure_server(mock_server, fetch):
    mock_server.add("/a.zip", mock_server.file(DATA))
    fetch(mock_server.url("/a.zip"), context=BrowserContext(referrer="https://example.com/p"))
    assert referers(mock_server) == [None]


def test_without_a_browser_no_referer_is_sent(mock_server, fetch):
    mock_server.add("/a.zip", mock_server.file(DATA))
    fetch(mock_server.url("/a.zip"))
    assert referers(mock_server) == [None]


def test_each_redirect_hop_gets_the_rule_for_its_own_site(mock_server, other_server, fetch):
    # page on site A -> link on site B redirects to site A: B gets the origin, A the full page
    page = mock_server.url("/page.html?x=1")
    other_server.add("/go", other_server.redirect(mock_server.url("/a.zip")))
    mock_server.add("/a.zip", mock_server.file(DATA))
    fetch(other_server.url("/go"), context=BrowserContext(referrer=page))
    assert referers(other_server) == [mock_server.url("/")]
    assert referers(mock_server) == [page]


def test_every_connection_of_a_split_download_sends_it(mock_server, fetch):
    data = os.urandom(4 * 1024 * 1024)
    mock_server.add("/big.bin", mock_server.ranged(data, etag='"v1"'))
    page = mock_server.url("/page.html")
    result = fetch(
        mock_server.url("/big.bin"),
        context=BrowserContext(referrer=page),
        settings=DownloadSettings(read_timeout=5.0, backoff_base=0.0, max_connections=4),
    )
    assert result.path.read_bytes() == data
    assert len(mock_server.requests) >= 4  # the first connection plus the extra parts
    assert set(referers(mock_server)) == {page}


def test_a_resume_sends_it_too(mock_server, fetch, tmp_path):
    from sdm.core.downloads import PartialDownload

    data = os.urandom(100_000)
    mock_server.add("/a.bin", mock_server.ranged(data, etag='"v1"'))
    part = tmp_path / "a.bin.sdmpart"
    part.write_bytes(data[:40_000])
    partial = PartialDownload(part, "a.bin", len(data), '"v1"', None, True)
    page = mock_server.url("/page.html")
    result = fetch(mock_server.url("/a.bin"), resume_from=partial,
                   context=BrowserContext(referrer=page))  # fmt: skip
    assert result.path.read_bytes() == data
    assert mock_server.requests[0]["Range"] == "bytes=40000-"
    assert referers(mock_server) == [page]


def test_the_browsers_name_is_used_when_the_server_gives_none(mock_server, fetch):
    mock_server.add("/download", mock_server.file(DATA))
    result = fetch(mock_server.url("/download"),
                   context=BrowserContext(suggested_name="Report 2026.pdf"))  # fmt: skip
    assert result.path.name == "Report 2026.pdf"


def test_the_servers_name_wins_over_the_browsers(mock_server, fetch):
    disposition = {"Content-Disposition": 'attachment; filename="server.zip"'}
    mock_server.add("/download", mock_server.file(DATA, headers=disposition))
    result = fetch(mock_server.url("/download"),
                   context=BrowserContext(suggested_name="browser.zip"))  # fmt: skip
    assert result.path.name == "server.zip"


def test_the_browsers_name_is_sanitized(mock_server, fetch, tmp_path):
    mock_server.add("/download", mock_server.file(DATA))
    result = fetch(mock_server.url("/download"),
                   context=BrowserContext(suggested_name='CON<1>?.txt'))  # fmt: skip
    assert result.path.parent == tmp_path
    assert result.path.name not in ("CON", "CON.txt")
    assert not any(ch in result.path.name for ch in "<>?")


class _FakeResponse:
    def __init__(self, status, location=None):
        self.status = status
        self.headers = {"Location": location} if location else {}

    def release(self):
        pass


class _FakeSession:
    """Answers each URL from a script and records the headers of every request."""

    def __init__(self, script):
        self.script = script
        self.seen = []

    async def get(self, url, allow_redirects, headers):
        self.seen.append((url, dict(headers or {})))
        return self.script[url]


def follow(session, url, referrer=None):
    return asyncio.run(
        http_download._get_following_redirects(
            session, url, NetworkPolicy(), DownloadSettings(), None, referrer
        )
    )


def test_a_redirect_from_https_to_http_is_refused():
    session = _FakeSession({
        "https://secure.example/a.zip": _FakeResponse(302, "http://plain.example/a.zip"),
        "http://plain.example/a.zip": _FakeResponse(200),
    })  # fmt: skip
    with pytest.raises(DownloadError, match=r"secure \(https\) address to an insecure"):
        follow(session, "https://secure.example/a.zip")
    assert [url for url, _ in session.seen] == ["https://secure.example/a.zip"]  # never asked


def test_redirects_that_stay_secure_are_followed_with_the_referer():
    session = _FakeSession({
        "https://site.example/get": _FakeResponse(302, "https://cdn.example/a.zip"),
        "https://cdn.example/a.zip": _FakeResponse(200),
    })  # fmt: skip
    response = follow(session, "https://site.example/get", "https://site.example/page?id=7")
    assert response.status == 200
    assert [headers.get("Referer") for _, headers in session.seen] == [
        "https://site.example/page?id=7",
        "https://site.example/",
    ]
