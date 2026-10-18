"""Messages from the browser are untrusted: anything but the exact request is refused (M7)."""

import pytest

from sdm.bridge.protocol import ProtocolError, parse_request

URL = "https://example.com/a.zip"


@pytest.mark.parametrize(
    "message",
    [
        None,
        [],
        "download",
        {},
        {"version": 1, "type": "download"},  # no url
        {"version": 1, "url": URL},  # no type
        # Extra fields could smuggle in a folder, a file name, headers or cookies.
        {"version": 1, "type": "download", "url": URL, "folder": "C:\\Windows\\System32"},
        {"version": 1, "type": "download", "url": URL, "filename": "..\\..\\evil.exe"},
        {"version": 1, "type": "download", "url": URL, "headers": {"Cookie": "a=b"}},
        {"version": 1, "type": "download", "url": URL, "allow_local_network": True},
        {"version": 2, "type": "download", "url": URL},
        {"version": "1", "type": "download", "url": URL},
        {"version": True, "type": "download", "url": URL},  # bool is an int in Python
        {"version": 1.0, "type": "download", "url": URL},
        {"version": 1, "type": "open", "url": URL},
        {"version": 1, "type": "run", "url": "C:\\Windows\\notepad.exe"},
        {"version": 1, "type": "download", "url": ["https://example.com"]},
        {"version": 1, "type": "download", "url": None},
    ],
)
def test_malformed_requests_are_refused(message):
    with pytest.raises(ProtocolError):
        parse_request(message)


@pytest.mark.parametrize(
    "url",
    [
        "file:///C:/Windows/win.ini",
        "javascript:alert(1)",
        "data:text/plain,hi",
        "ftp://example.com/a.zip",
        "\\\\server\\share\\a.zip",  # a Windows network path
        "C:\\Users\\me\\a.zip",
        "https://user:pass@example.com/a.zip",
        "https://example.com/a b.zip",
        "https://example.com/a\r\nX-Injected: 1",
        "https://example.com:99999/a.zip",
        "https://example.com/" + "a" * 9000,
        "",
    ],
)
def test_unsafe_urls_are_refused(url):
    with pytest.raises(ProtocolError):
        parse_request({"version": 1, "type": "download", "url": url})


def test_private_addresses_pass_the_schema_but_not_the_network_policy():
    # The schema checks shape only; the download still goes through the SSRF policy
    # (ADR-0007), which blocks 127.0.0.1 and 192.168.x.x unless the user allows them.
    assert parse_request({"version": 1, "type": "download", "url": "http://127.0.0.1/a"}).url
