"""Chrome's native messaging format and the one request SDM accepts from the browser.

Chrome talks to a native host over the host's stdin and stdout. Each message is a 4-byte
length in native byte order (little-endian on Windows) followed by that many bytes of UTF-8
JSON. Everything that arrives is untrusted: the size is capped before anything is read, and
the request must match the schema exactly (no extra fields, so no paths or options can be
smuggled in).
"""

import json
import struct
from dataclasses import dataclass
from typing import BinaryIO

from sdm.core.errors import InvalidURLError, SDMError
from sdm.core.urls import MAX_URL_LENGTH, validate_url

PROTOCOL_VERSION = 1
# Chrome allows up to 64 MiB towards a host; a link address needs far less. Anything bigger
# is refused before its body is read.
MAX_MESSAGE_BYTES = 64 * 1024
_HEADER = struct.Struct("=I")  # native byte order, unsigned 32-bit, as Chrome writes it
_REQUEST_KEYS = frozenset({"version", "type", "url"})


class ProtocolError(SDMError):
    """A message that isn't a well-formed, allowed request."""


@dataclass(frozen=True)
class DownloadRequest:
    url: str


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
    """Check a decoded message against the schema {"version": 1, "type": "download", "url"}."""
    if not isinstance(value, dict):
        raise ProtocolError("The message must be a JSON object.")
    if set(value) != _REQUEST_KEYS:
        raise ProtocolError("The message must have exactly the fields version, type and url.")
    version = value["version"]
    # bool is a subclass of int in Python: true must not pass as version 1.
    if type(version) is not int or version != PROTOCOL_VERSION:
        raise ProtocolError("Unsupported message version.")
    if value["type"] != "download":
        raise ProtocolError("Unsupported message type.")
    url = value["url"]
    if not isinstance(url, str) or len(url) > MAX_URL_LENGTH:
        raise ProtocolError("The url field must be a string of at most 8192 characters.")
    try:
        validate_url(url)
    except InvalidURLError as exc:
        raise ProtocolError(str(exc)) from None
    return DownloadRequest(url.strip())


def request_message(url: str) -> dict[str, object]:
    """The request as the extension sends it (used by tests and the pipe client)."""
    return {"version": PROTOCOL_VERSION, "type": "download", "url": url}


def _read_exactly(stream: BinaryIO, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            raise ProtocolError("The message ended early.")
        data += chunk
    return data
