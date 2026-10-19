"""The Referer header SDM sends for downloads that came from the browser (M8, ADR-0015).

SDM follows the browser's default rule, "strict-origin-when-cross-origin":

- same site (scheme, host and port all equal): the page's full address, without its fragment;
- another site: only the page's origin, e.g. "https://example.com/";
- never from a secure (https) page to an insecure (http) server: no Referer at all.

The page address comes from the browser and is untrusted: anything that isn't a plain
http(s) URL is dropped rather than sent.
"""

from urllib.parse import SplitResult, urlsplit, urlunsplit

from sdm.core.errors import InvalidURLError
from sdm.core.urls import validate_url

_DEFAULT_PORTS = {"http": 80, "https": 443}


def referer_header(referrer: str | None, target_url: str) -> str | None:
    """The Referer value to send with a request to `target_url`, or None for none."""
    if not referrer:
        return None
    try:
        page = validate_url(referrer)
        target = urlsplit(target_url.strip())
        target_port = target.port
    except (InvalidURLError, ValueError):
        return None
    page_scheme, target_scheme = page.scheme.lower(), target.scheme.lower()
    if page_scheme == "https" and target_scheme != "https":
        return None  # a secure page's address never goes to an insecure server
    if _origin(page_scheme, page.hostname, page.port) == _origin(
        target_scheme, target.hostname, target_port
    ):
        return urlunsplit((page_scheme, _netloc(page), page.path or "/", page.query, ""))
    return urlunsplit((page_scheme, _netloc(page), "/", "", ""))


def check_redirect(current_url: str, next_url: str) -> bool:
    """False when a redirect would go from https down to http (SDM refuses those)."""
    # Only the scheme matters, and splitting the whole URL can raise on a malformed address
    # such as "http://[" (found by fuzzing, M10); validate_url refuses those on the next hop.
    current = current_url.strip().split(":", 1)[0].lower()
    following = next_url.strip().split(":", 1)[0].lower()
    return not (current == "https" and following == "http")


def _origin(scheme: str, host: str | None, port: int | None) -> tuple[str, str, int | None]:
    return scheme, (host or "").lower(), port if port is not None else _DEFAULT_PORTS.get(scheme)


def _netloc(parts: SplitResult) -> str:
    host = parts.hostname or ""
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    port = parts.port
    return f"{host}:{port}" if port is not None else host
