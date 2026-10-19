"""Version 2 messages: the browser's extra hints are optional and strictly checked (M8)."""

import pytest

from sdm.bridge.protocol import DownloadRequest, ProtocolError, parse_request
from sdm.core.downloads import BrowserContext

URL = "https://example.com/files/a.zip?token=abc"
PAGE = "https://example.com/files/"


def v2(**fields):
    return {"version": 2, "type": "download", "url": URL, **fields}


def test_a_full_version_2_message():
    request = parse_request(
        v2(referrer=PAGE, filename="a.zip", size=1234, mime="application/zip", source="capture")
    )
    assert request == DownloadRequest(URL, PAGE, "a.zip", 1234, "application/zip", "capture")
    assert request.context() == BrowserContext(referrer=PAGE, suggested_name="a.zip")


def test_every_hint_is_optional():
    request = parse_request(v2())
    assert request == DownloadRequest(URL)
    assert request.source == "menu"
    assert request.context() is None


def test_version_1_still_works_but_cant_carry_hints():
    assert parse_request({"version": 1, "type": "download", "url": URL}) == DownloadRequest(URL)
    with pytest.raises(ProtocolError):
        parse_request({"version": 1, "type": "download", "url": URL, "referrer": PAGE})


def test_the_message_round_trips_through_the_host():
    request = DownloadRequest(URL, PAGE, "a.zip", 0, "application/zip", "capture")
    assert parse_request(request.to_message()) == request
    assert parse_request(DownloadRequest(URL).to_message()) == DownloadRequest(URL)


@pytest.mark.parametrize(
    "fields",
    [
        # still nothing beyond the schema
        {"headers": {"Cookie": "session=1"}},
        {"cookies": "session=1"},
        {"folder": "C:\\Windows"},
        {"path": "C:\\Users\\me\\a.zip"},
        {"allow_local_network": True},
        # referrer: only an http(s) address
        {"referrer": "file:///C:/Users/me/page.html"},
        {"referrer": "javascript:alert(1)"},
        {"referrer": "https://user:pass@example.com/"},
        {"referrer": "https://example.com/\r\nX-Injected: 1"},
        {"referrer": ""},
        {"referrer": None},
        {"referrer": 7},
        {"referrer": "https://example.com/" + "a" * 9000},
        # filename: a bare name, never a path or a stream
        {"filename": "..\\..\\Windows\\evil.exe"},
        {"filename": "../../evil.exe"},
        {"filename": "C:evil.exe"},
        {"filename": "a.zip:hidden"},
        {"filename": "evil\x00.exe"},
        {"filename": "line\nbreak.txt"},
        {"filename": ".."},
        {"filename": " . "},
        {"filename": ""},
        {"filename": "a" * 256},
        {"filename": ["a.zip"]},
        # size and mime: plain values only
        {"size": -1},
        {"size": 2**53 + 1},
        {"size": 1.5},
        {"size": "100"},
        {"size": True},
        {"mime": "text/plain\r\nX: 1"},
        {"mime": "a" * 201},
        {"mime": ""},
        {"mime": 5},
        # source: one of two words
        {"source": "page-script"},
        {"source": None},
    ],
)
def test_bad_hints_are_refused(fields):
    with pytest.raises(ProtocolError):
        parse_request(v2(**fields))


def test_odd_but_harmless_names_are_kept_for_the_sanitizer():
    # Reserved names and odd characters aren't paths: the engine's sanitizer handles them.
    for name in ("CON", "a<b>.zip", "naïve résumé.pdf", "file.tar.gz"):
        assert parse_request(v2(filename=name)).filename == name
