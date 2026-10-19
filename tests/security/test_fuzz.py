"""Fuzz tests (M10): thousands of random and malformed inputs for every parser of untrusted data.

Standard library only (owner's choice): a fixed seed makes every run identical, so a failure
can always be reproduced. Each test asserts two things: nothing raises anything but the
parser's own error, and whatever is accepted is actually safe.
"""

import io
import json
import random
import struct

import pytest

from sdm.bridge.protocol import MAX_MESSAGE_BYTES, ProtocolError, parse_request, read_message
from sdm.core.checksums import InvalidChecksumError, normalize_sha256
from sdm.core.errors import InvalidURLError
from sdm.core.filenames import (
    _RESERVED_NAMES,
    filename_from_content_disposition,
    filename_from_url,
    sanitize_filename,
)
from sdm.core.referrer import check_redirect, referer_header
from sdm.core.segments import decode_segments, segments_cover
from sdm.core.urls import validate_url
from sdm.engine.segmented import parse_content_range

ROUNDS = 3000
SEED = 20261020

# Pieces that have broken parsers before, anywhere: separators, device names, controls,
# bidi overrides, lone UTF-16 surrogates (valid in JSON as "\ud800"), odd digits, huge numbers.
NASTY = [
    "/", "\\", ":", "..", ".", " ", "\x00", "\r\n", "\t", "\x7f", "%", "%00", "%2F", "%5C",
    "CON", "nul", "COM1", "LPT¹", "‮", "‏", "⁦", "\ud800", "\udfff", "\U0001f600",
    "／", "∕", "٠", "²", "é", "é", "ﬁ", '"', "'", ";", "=", "*", "?",
    "<", ">", "|", "filename=", "filename*=", "UTF-8''", "bytes ", "-", "/", "http://",
    "https://", "file:///", "javascript:", "@", "[::1]", "127.0.0.1", "0x7f.1", "99999999999",
    "-1", "1e9", "　", "﻿", "sha256:", "a" * 300,
]  # fmt: skip


def nasty_text(rng: random.Random, max_parts: int = 8) -> str:
    parts = []
    for _ in range(rng.randint(0, max_parts)):
        if rng.random() < 0.6:
            parts.append(rng.choice(NASTY))
        else:
            parts.append("".join(chr(rng.randint(0x20, 0x2FFF)) for _ in range(rng.randint(1, 6))))
    return "".join(parts)


def nasty_json(rng: random.Random, depth: int = 0):
    kind = rng.randint(0, 7 if depth < 3 else 4)
    if kind == 0:
        return nasty_text(rng)
    if kind == 1:
        return rng.choice([0, 1, 2, -1, 2**53, 2**53 + 1, 2**64, 10**30, 1.5, float("1e308")])
    if kind == 2:
        return rng.choice([True, False, None])
    if kind == 3:
        return "https://example.com/" + nasty_text(rng, 3)
    if kind == 4:
        return rng.choice(["menu", "capture", "download", 1, 2, "1", "2"])
    if kind == 5:
        return [nasty_json(rng, depth + 1) for _ in range(rng.randint(0, 3))]
    keys = ["version", "type", "url", "referrer", "filename", "size", "mime", "source",
            "folder", "headers", nasty_text(rng, 2)]  # fmt: skip
    return {rng.choice(keys): nasty_json(rng, depth + 1) for _ in range(rng.randint(0, 9))}


@pytest.fixture
def rng():
    return random.Random(SEED)  # noqa: S311 - test data, not security


def assert_safe_name(name: str) -> None:
    assert name and len(name.encode("utf-16-le", "surrogatepass")) // 2 <= 200
    assert not any(ch in name for ch in '<>:"/\\|?*') and all(ord(ch) >= 0x20 for ch in name)
    assert "\x7f" not in name and not name.endswith((".", " "))
    assert name.split(".", 1)[0].rstrip(" ").upper() not in _RESERVED_NAMES
    assert not any("\ud800" <= ch <= "\udfff" for ch in name), "lone surrogates can't be saved"


def test_browser_messages(rng):
    accepted = 0
    for _ in range(ROUNDS):
        message = nasty_json(rng)
        if isinstance(message, dict) and rng.random() < 0.5:  # many near-valid messages too
            message.update({"version": rng.choice([1, 2]), "type": "download"})
            message.setdefault("url", "https://example.com/" + nasty_text(rng, 2))
        try:
            request = parse_request(message)
        except ProtocolError:
            continue
        accepted += 1
        validate_url(request.url)
        if request.referrer is not None:
            validate_url(request.referrer)
        if request.filename is not None:
            assert not any(ch in request.filename for ch in "/\\:")
            assert_safe_name(sanitize_filename(request.filename))
    assert accepted > 50  # the fuzzer also reached the accepting paths


def test_framed_messages(rng):
    for _ in range(ROUNDS):
        body = json.dumps(nasty_json(rng)).encode("utf-8", "surrogatepass")
        if rng.random() < 0.3:
            body = bytes(rng.randint(0, 255) for _ in range(rng.randint(0, 40)))
        length = rng.choice([len(body), len(body) + 3, max(0, len(body) - 2),
                             MAX_MESSAGE_BYTES + 1, 2**32 - 1])  # fmt: skip
        stream = io.BytesIO(struct.pack("<I", length) + body)
        try:
            read_message(stream)
        except ProtocolError:
            pass


def test_file_names(rng):
    for _ in range(ROUNDS):
        assert_safe_name(sanitize_filename(nasty_text(rng)))
        assert_safe_name(sanitize_filename(nasty_text(rng), max_length=rng.randint(12, 200)) or "x")


def test_content_disposition_and_url_names(rng):
    for _ in range(ROUNDS):
        header = rng.choice(["attachment; ", "inline;", "", "attachment;filename*=UTF-8''"])
        header += nasty_text(rng)
        name = filename_from_content_disposition(header)
        assert name is None or isinstance(name, str)
        assert_safe_name(sanitize_filename(name))
        url_name = filename_from_url("https://example.com/" + nasty_text(rng))
        assert_safe_name(sanitize_filename(url_name))


def test_content_range(rng):
    for _ in range(ROUNDS):
        if rng.random() < 0.5:
            a, b, c = (rng.randint(-5, 10**12) for _ in range(3))
            value = f"bytes {a}-{b}/{c}" + rng.choice(["", " ", "x", "٠", "/1"])
        else:
            value = "bytes " + nasty_text(rng, 4)
        parsed = parse_content_range(value)
        if parsed is not None:
            first, last, total = parsed
            assert 0 <= first <= last < total


def test_saved_parts_maps(rng):
    for _ in range(ROUNDS):
        total = rng.randint(1, 10**9)
        text = json.dumps(nasty_json(rng)) if rng.random() < 0.7 else nasty_text(rng)
        segments = decode_segments(text, total)
        if segments is not None:
            assert segments_cover(segments, total)


def test_urls_and_referers(rng):
    for _ in range(ROUNDS):
        url = rng.choice(["http://", "https://", "", "HTTPS://"]) + nasty_text(rng)
        try:
            validate_url(url)
        except InvalidURLError:
            pass
        referer = referer_header(url, "https://example.com/a.zip")
        if referer is not None:
            assert referer.startswith(("http://", "https://"))
            assert not any(ch.isspace() or ord(ch) < 0x20 for ch in referer)
        assert isinstance(check_redirect(url, "http://example.com/" + nasty_text(rng, 2)), bool)


def test_checksums(rng):
    for _ in range(ROUNDS):
        text = (
            nasty_text(rng)
            if rng.random() < 0.7
            else "".join(
                rng.choice("0123456789abcdefABCDEF \n") for _ in range(rng.randint(60, 70))
            )
        )
        try:
            value = normalize_sha256(text)
        except InvalidChecksumError:
            continue
        assert value is None or (len(value) == 64 and set(value) <= set("0123456789abcdef"))


def test_saved_settings(rng, tmp_path):
    from sdm.storage.database import DownloadStore
    from sdm.ui.preferences import Preferences, load_preferences

    store = DownloadStore(tmp_path / "sdm.db")
    try:
        keys = [f"prefs.{name}" for name in Preferences.__dataclass_fields__]
        for _ in range(300):
            for key in keys:
                text = nasty_text(rng, 3).encode("utf-8", "replace").decode("utf-8")
                store.set_setting(key, text)
            preferences = load_preferences(store)
            assert preferences == preferences.checked()
    finally:
        store.close()
