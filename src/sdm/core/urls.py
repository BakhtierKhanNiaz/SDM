"""Checking URLs before SDM touches the network, and making them safe to log."""

from urllib.parse import SplitResult, urlsplit, urlunsplit

from sdm.core.errors import InvalidURLError

ALLOWED_SCHEMES = frozenset({"http", "https"})
MAX_URL_LENGTH = 8192


def validate_url(url: str) -> SplitResult:
    """Return the parsed URL if SDM may download from it, else raise InvalidURLError.

    This checks the URL's shape only. Whether its host is an allowed destination is the
    network policy's job (sdm.engine.policy), because that needs the resolved IP address.
    """
    url = url.strip()
    if not url:
        raise InvalidURLError("The URL is empty.")
    if len(url) > MAX_URL_LENGTH:
        raise InvalidURLError(f"The URL is longer than {MAX_URL_LENGTH} characters.")
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in url):
        raise InvalidURLError("The URL contains spaces or control characters.")

    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        shown = f"'{scheme}:'" if scheme else "no scheme"
        raise InvalidURLError(f"Only http:// and https:// URLs are supported (got {shown}).")
    if parts.username is not None or parts.password is not None:
        raise InvalidURLError("URLs with an embedded user name or password are not supported.")
    if not parts.hostname:
        raise InvalidURLError("The URL has no server name.")
    try:
        _ = parts.port  # raises ValueError for ports like 99999 or "abc"
    except ValueError:
        raise InvalidURLError("The URL has an invalid port number.") from None
    return parts


def redact_url(url: str) -> str:
    """Return the URL without credentials, query string or fragment, for logs and messages.

    Query strings often carry access tokens (signed download links), so they never reach logs.
    """
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        return "<invalid URL>"
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    netloc = f"{host}:{port}" if port else host
    redacted = urlunsplit((parts.scheme, netloc, parts.path, "", ""))
    return redacted + ("?<redacted>" if parts.query else "")
