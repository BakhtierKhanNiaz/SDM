"""Checking a finished file against the SHA-256 its publisher gives (M9, ADR-0016)."""

import hashlib
import re
from pathlib import Path

from sdm.core.errors import SDMError

CHECKING, VERIFIED, MISMATCH, MISSING = "checking", "verified", "mismatch", "missing"
CHUNK = 1024 * 1024
_HEX64 = re.compile(r"[0-9a-f]{64}")


class InvalidChecksumError(SDMError):
    """Text that isn't a SHA-256 value."""


def normalize_sha256(text: str | None) -> str | None:
    """A SHA-256 as 64 lowercase hex digits, or None for empty text.

    Accepts what publishers print: upper or lower case, spaces or line breaks in the middle
    (python.org splits it over two lines), and an optional "sha256:" or "SHA256 " prefix.
    """
    value = re.sub(r"\s+", "", text or "").lower()
    for prefix in ("sha256:", "sha256="):
        value = value.removeprefix(prefix)
    if not value:
        return None
    if value.startswith("sha256") and _HEX64.fullmatch(value[6:]):
        value = value[6:]
    if not _HEX64.fullmatch(value):
        raise InvalidChecksumError(
            "A SHA-256 checksum is 64 characters from 0-9 and a-f (spaces are ignored)."
        )
    return value


def sha256_of(path: Path) -> str:
    """The file's SHA-256 (reads it in 1 MiB pieces; run it off the window's thread)."""
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while chunk := file.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()
