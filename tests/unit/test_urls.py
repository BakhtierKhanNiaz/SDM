"""URL checks and log redaction."""

import pytest

from sdm.core.errors import InvalidURLError
from sdm.core.urls import redact_url, validate_url


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/file.zip",
        "https://example.com:8443/a/b?x=1",
        "HTTPS://EXAMPLE.COM/",
        "  https://example.com/padded  ",
        "http://[2001:db8::1]/f",
    ],
)
def test_accepts_http_and_https(url):
    assert validate_url(url).hostname


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("", "empty"),
        ("ftp://example.com/f", "'ftp:'"),
        ("file:///C:/Windows/win.ini", "'file:'"),
        ("javascript:alert(1)", "'javascript:'"),
        ("data:text/plain,hi", "'data:'"),
        ("example.com/file.zip", "no scheme"),
        ("http://user:secret@example.com/f", "user name or password"),
        ("http://user@example.com/f", "user name or password"),
        ("http:///path-only", "no server name"),
        ("http://example.com:99999/f", "invalid port"),
        ("http://example.com/a b", "spaces"),
        ("http://example.com/\x00", "control characters"),
        ("http://example.com/" + "a" * 9000, "longer than"),
    ],
)
def test_rejects_unsupported_urls(url, reason):
    with pytest.raises(InvalidURLError, match=reason):
        validate_url(url)


def test_redact_removes_credentials_query_and_fragment():
    url = "https://user:pw@example.com:8443/dl/file.zip?token=abc#frag"
    assert redact_url(url) == "https://example.com:8443/dl/file.zip?<redacted>"


def test_redact_keeps_plain_urls():
    assert redact_url("http://example.com/a.zip") == "http://example.com/a.zip"


def test_redact_keeps_ipv6_brackets():
    assert redact_url("http://[::1]:8080/x") == "http://[::1]:8080/x"


def test_redact_handles_invalid_urls():
    assert redact_url("http://example.com:99999/") == "<invalid URL>"
