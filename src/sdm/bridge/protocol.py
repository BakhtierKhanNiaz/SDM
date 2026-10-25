"""Chrome's native messaging format and the one request SDM accepts from the browser.

Chrome talks to a native host over the host's stdin and stdout. Each message is a 4-byte
length in native byte order (little-endian on Windows) followed by that many bytes of UTF-8
JSON. Everything that arrives is untrusted: the size is capped before anything is read, and
the request must match the schema exactly (no extra fields, so no paths or options can be
smuggled in).

Version 1 (M7): {"version": 1, "type": "download", "url": ...}, exactly those fields.
Version 2 (M8) may add what the browser knew, each field optional and strictly checked:
"referrer" (the page, an http(s) URL), "filename" (a bare name, never a path), "size" (bytes),
"mime" and "source" ("menu" or "capture"). Still no headers, cookies, folders or options.
M12: "source" may also be "video": the url is a web page the user wants as a video (the
extension's "Download this video with SDM"); SDM still asks before anything downloads.
"""

import json
import re
import struct
from dataclasses import dataclass
from typing import BinaryIO

from sdm.core.downloads import BrowserContext
from sdm.core.errors import InvalidURLError, SDMError
from sdm.core.urls import MAX_URL_LENGTH, validate_url

PROTOCOL_VERSION = 2  # the newest version; 1 is still accepted
# Chrome allows up to 64 MiB towards a host; a link address needs far less. Anything bigger
# is refused before its body is read.
MAX_MESSAGE_BYTES = 64 * 1024
MAX_FILENAME_LENGTH = 255
MAX_MIME_LENGTH = 200
MAX_SIZE = 2**53  # the largest whole number JavaScript represents exactly
SOURCES = frozenset({"menu", "capture", "video"})
_HEADER = struct.Struct("=I")  # native byte order, unsigned 32-bit, as Chrome writes it
_REQUIRED_KEYS = frozenset({"version", "type", "url"})
_OPTIONAL_KEYS = {1: frozenset(), 2: frozenset({"referrer", "filename", "size", "mime", "source"})}
# A file name must not reach outside the folder or name a stream: no separators, no colon.
_FORBIDDEN_IN_NAME = frozenset("/\\:")
_SURROGATE = re.compile(r"[\ud800-\udfff]")


class ProtocolError(SDMError):
    """A message that isn't a well-formed, allowed request."""


@dataclass(frozen=True)
class DownloadRequest:
    url: str
    referrer: str | None = None
    filename: str | None = None
    size: int | None = None
    mime: str | None = None
    source: str = "menu"

    def context(self) -> BrowserContext | None:
        """What the engine and the history keep (size, type and source are only shown)."""
        if self.referrer is None and self.filename is None:
            return None
        return BrowserContext(self.referrer, self.filename)

    def to_message(self) -> dict[str, object]:
        """The request as a version 2 message (the host passes it on to the app)."""
        message: dict[str, object] = {"version": PROTOCOL_VERSION, "type": "download"}
        message["url"] = self.url
        optional = {"referrer": self.referrer, "filename": self.filename, "size": self.size,
                    "mime": self.mime}  # fmt: skip
        message.update({key: value for key, value in optional.items() if value is not None})
        message["source"] = self.source
        return message


def read_message(stream: BinaryIO) -> object:
    """Read one framed message and return the decoded JSON value."""
    header = _read_exactly(stream, _HEADER.size)
    (length,) = _HEADER.unpack(header)
    if length > MAX_MESSAGE_BYTES:
        raise ProtocolError(f"The message is too long ({length} bytes).")
    return decode_json(_read_exactly(stream, length))


def write_message(stream: BinaryIO, value: object) -> None:
    """Write one framed message (compact JSON) and flush it."""
    body = encode_json(value)
    stream.write(_HEADER.pack(len(body)) + body)
    stream.flush()


def encode_json(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def decode_json(data: bytes) -> object:
    if len(data) > MAX_MESSAGE_BYTES:
        raise ProtocolError(f"The message is too long ({len(data)} bytes).")
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):  # JSONDecodeError is a ValueError
        raise ProtocolError("The message isn't valid UTF-8 JSON.") from None


def parse_request(value: object) -> DownloadRequest:
    """Check a decoded message against the schema (version 1 or 2) and return the request."""
    if not isinstance(value, dict):
        raise ProtocolError("The message must be a JSON object.")
    version = value.get("version")
    # bool is a subclass of int in Python: true must not pass as version 1.
    if type(version) is not int or version not in _OPTIONAL_KEYS:
        raise ProtocolError("Unsupported message version.")
    keys = set(value)
    if not _REQUIRED_KEYS <= keys or keys - _REQUIRED_KEYS - _OPTIONAL_KEYS[version]:
        allowed = ", ".join(sorted(_REQUIRED_KEYS | _OPTIONAL_KEYS[version]))
        raise ProtocolError(f"The message has fields other than the allowed ones ({allowed}).")
    if value["type"] != "download":
        raise ProtocolError("Unsupported message type.")
    url = _checked_url(value["url"], "url")
    return DownloadRequest(
        url=url,
        referrer=_checked_url(value["referrer"], "referrer") if "referrer" in value else None,
        filename=_checked_filename(value["filename"]) if "filename" in value else None,
        size=_checked_size(value["size"]) if "size" in value else None,
        mime=_checked_mime(value["mime"]) if "mime" in value else None,
        source=_checked_source(value["source"]) if "source" in value else "menu",
    )


def request_message(url: str) -> dict[str, object]:
    """A version 1 request as the M7 extension sends it (used by tests)."""
    return {"version": 1, "type": "download", "url": url}


def _checked_url(url: object, field: str) -> str:
    if not isinstance(url, str) or len(url) > MAX_URL_LENGTH:
        raise ProtocolError(f"The {field} field must be a string of at most 8192 characters.")
    try:
        validate_url(url)
    except InvalidURLError as exc:
        raise ProtocolError(f"The {field} field: {exc}") from None
    return url.strip()


def _checked_filename(name: object) -> str:
    if not isinstance(name, str) or not 0 < len(name) <= MAX_FILENAME_LENGTH:
        raise ProtocolError("The filename field must be a string of 1 to 255 characters.")
    if any(ch in _FORBIDDEN_IN_NAME or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in name):
        raise ProtocolError("The filename field must be a bare file name, not a path.")
    if not name.strip(" ."):
        raise ProtocolError("The filename field must be a real file name.")
    if _SURROGATE.search(name):  # lone UTF-16 surrogates, which JSON allows (fuzzing, M10)
        raise ProtocolError("The filename field contains broken characters.")
    return name


def _checked_size(size: object) -> int:
    if type(size) is not int or not 0 <= size <= MAX_SIZE:
        raise ProtocolError("The size field must be a whole number of bytes.")
    return size


def _checked_mime(mime: object) -> str:
    if (
        not isinstance(mime, str)
        or not 0 < len(mime) <= MAX_MIME_LENGTH
        or not all(0x20 < ord(ch) < 0x7F for ch in mime)
    ):
        raise ProtocolError("The mime field must be a short media type such as text/plain.")
    return mime


def _checked_source(source: object) -> str:
    # isinstance first: `[] in SOURCES` raises TypeError (found by fuzzing, M10).
    if not isinstance(source, str) or source not in SOURCES:
        raise ProtocolError("The source field must be menu, capture or video.")
    return str(source)


def _read_exactly(stream: BinaryIO, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            raise ProtocolError("The message ended early.")
        data += chunk
    return data
