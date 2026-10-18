"""Native messaging framing and the request schema (M7)."""

import io
import struct

import pytest

from sdm.bridge.protocol import (
    MAX_MESSAGE_BYTES,
    DownloadRequest,
    ProtocolError,
    parse_request,
    read_message,
    request_message,
    write_message,
)

URL = "https://example.com/files/a.zip?token=abc"


def framed(body: bytes) -> io.BytesIO:
    return io.BytesIO(struct.pack("<I", len(body)) + body)


def test_round_trip():
    stream = io.BytesIO()
    write_message(stream, {"ok": True})
    assert stream.getvalue() == b"\x0b\x00\x00\x00" + b'{"ok":true}'  # little-endian length
    stream.seek(0)
    assert read_message(stream) == {"ok": True}


def test_reads_exactly_one_message():
    stream = io.BytesIO(framed(b'{"a":1}').getvalue() + framed(b'{"b":2}').getvalue())
    assert read_message(stream) == {"a": 1}
    assert read_message(stream) == {"b": 2}


def test_valid_request():
    assert parse_request(request_message(URL)) == DownloadRequest(URL)


def test_a_huge_length_is_refused_before_reading_the_body():
    stream = io.BytesIO(struct.pack("<I", MAX_MESSAGE_BYTES + 1))  # no body follows
    with pytest.raises(ProtocolError, match="too long"):
        read_message(stream)


def test_the_largest_allowed_message_is_read():
    body = b'"' + b"a" * (MAX_MESSAGE_BYTES - 2) + b'"'
    assert len(read_message(framed(body))) == MAX_MESSAGE_BYTES - 2


@pytest.mark.parametrize(
    "raw",
    [
        b"",  # nothing at all
        b"\x05\x00",  # half a header
        struct.pack("<I", 10) + b"{}",  # body shorter than promised
    ],
)
def test_cut_off_messages(raw):
    with pytest.raises(ProtocolError, match="ended early"):
        read_message(io.BytesIO(raw))


@pytest.mark.parametrize("body", [b"\xff\xfe{}", b"{not json", b'{"a":1}trailing'])
def test_bad_encoding_or_json(body):
    with pytest.raises(ProtocolError, match="valid UTF-8 JSON"):
        read_message(framed(body))
