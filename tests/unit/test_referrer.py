"""The Referer rules for downloads from the browser, and the https-to-http redirect check (M8)."""

import pytest

from sdm.core.referrer import check_redirect, referer_header

PAGE = "https://example.com/files/list?page=2#top"


@pytest.mark.parametrize(
    ("referrer", "target", "expected"),
    [
        # same site: the full page address, without the fragment
        (PAGE, "https://example.com/a.zip", "https://example.com/files/list?page=2"),
        (PAGE, "https://EXAMPLE.com:443/a.zip", "https://example.com/files/list?page=2"),
        ("http://example.com:8080/p", "http://example.com:8080/a", "http://example.com:8080/p"),
        ("http://example.com", "http://example.com/a.zip", "http://example.com/"),
        # another site, another port or another scheme: only the origin
        (PAGE, "https://cdn.example.net/a.zip", "https://example.com/"),
        ("http://example.com:8080/p?q=1", "http://example.com/a", "http://example.com:8080/"),
        ("http://example.com/p?q=1", "https://example.com/a", "http://example.com/"),
        ("http://[::1]:8000/p", "http://example.com/a", "http://[::1]:8000/"),
        # a secure page's address never goes to an insecure server
        (PAGE, "http://example.com/a.zip", None),
        (PAGE, "http://cdn.example.net/a.zip", None),
        # nothing usable: nothing sent
        (None, "https://example.com/a.zip", None),
        ("", "https://example.com/a.zip", None),
        ("file:///C:/Users/me/page.html", "https://example.com/a.zip", None),
        ("chrome://settings", "https://example.com/a.zip", None),
        ("https://user:secret@example.com/p", "https://example.com/a.zip", None),
        ("https://example.com/p\r\nX-Evil: 1", "https://example.com/a.zip", None),
        ("https://example.com/p", "https://example.com:99999/a.zip", None),
    ],
)
def test_referer_header(referrer, target, expected):
    assert referer_header(referrer, target) == expected


@pytest.mark.parametrize(
    ("current", "following", "allowed"),
    [
        ("https://a.example/x", "http://b.example/x", False),
        ("HTTPS://a.example/x", "HTTP://a.example/y", False),
        ("https://a.example/x", "https://b.example/x", True),
        ("http://a.example/x", "https://b.example/x", True),
        ("http://a.example/x", "http://b.example/x", True),
    ],
)
def test_https_to_http_redirects_are_refused(current, following, allowed):
    assert check_redirect(current, following) is allowed
