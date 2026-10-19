"""Choosing a safe Windows filename for a download.

Names come from untrusted sources (the Content-Disposition header or the URL), so they are
reduced to a single, valid path component before SDM uses them.
"""

import codecs
import os
import re
import unicodedata
from urllib.parse import unquote, urlsplit

FALLBACK_NAME = "download"

# Characters Windows forbids in file names, plus ASCII control characters.
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
# Lone UTF-16 surrogates (JSON allows "\ud800") can't be in a Windows file name (fuzzing, M10).
_SURROGATES = re.compile(r"[\ud800-\udfff]")
# Bidirectional-text controls: "invoice‮txt.exe" *displays* as "invoiceexe.txt".
_BIDI_CONTROLS = re.compile("[؜‎‏‪-‮⁦-⁩]")

# Device names Windows reserves regardless of extension ("CON.txt" is still the console).
_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in "123456789¹²³"}
    | {f"LPT{i}" for i in "123456789¹²³"}
)

# RFC 6266 / RFC 8187: filename*=charset'language'percent-encoded-value
_FILENAME_STAR = re.compile(r"(?:^|;)\s*filename\*\s*=\s*([^';\s]*)'[^']*'([^;\s]+)", re.IGNORECASE)
# filename="quoted \"value\"" or filename=token
_FILENAME_PLAIN = re.compile(
    r'(?:^|;)\s*filename\s*=\s*(?:"((?:[^"\\]|\\.)*)"|([^;\s]+))', re.IGNORECASE
)


def filename_from_content_disposition(value: str | None) -> str | None:
    """Extract the filename from a Content-Disposition header, or None.

    `filename*` (which can carry non-ASCII names) wins over `filename`, as RFC 6266 says.
    """
    if not value:
        return None
    star = _FILENAME_STAR.search(value)
    if star:
        charset = star.group(1) or "utf-8"
        try:
            codecs.lookup(charset)
        except LookupError:
            charset = "utf-8"
        name = unquote(star.group(2), encoding=charset, errors="replace")
        if name:
            return name
    plain = _FILENAME_PLAIN.search(value)
    if plain:
        quoted, token = plain.groups()
        name = re.sub(r"\\(.)", r"\1", quoted) if quoted is not None else token
        return name or None
    return None


def filename_from_url(url: str) -> str | None:
    """Return the last path segment of the URL, percent-decoded, or None if there is none."""
    path = urlsplit(url).path
    segment = path.rsplit("/", 1)[-1]
    return unquote(segment, errors="replace") or None


def _utf16_length(text: str) -> int:
    # Windows measures name limits in UTF-16 code units; an emoji counts as two.
    return len(text.encode("utf-16-le")) // 2


def _truncate(text: str, max_units: int) -> str:
    while text and _utf16_length(text) > max_units:
        text = text[:-1]
    return text


def sanitize_filename(name: str | None, max_length: int = 200) -> str:
    """Turn an untrusted name into one safe Windows file name (no folders, no device names).

    `max_length` is in UTF-16 code units and must be at least 12.
    """
    if not name:
        return FALLBACK_NAME
    # Keep only the last component, so "../../evil.exe" or "C:\\x\\evil.exe" cannot escape.
    name = re.split(r"[/\\]", name)[-1]
    name = unicodedata.normalize("NFC", name)
    name = _BIDI_CONTROLS.sub("", name)
    name = _INVALID_CHARS.sub("_", name)
    name = _SURROGATES.sub("_", name)
    # Windows silently drops trailing dots and spaces, which would change the name we chose.
    name = name.strip().rstrip(". ")
    if not name:
        return FALLBACK_NAME
    if name.split(".", 1)[0].rstrip(" ").upper() in _RESERVED_NAMES:
        name = "_" + name

    if _utf16_length(name) > max_length:
        stem, ext = os.path.splitext(name)
        if not ext or _utf16_length(ext) > min(16, max_length // 2):
            stem, ext = name, ""
        stem = _truncate(stem, max_length - _utf16_length(ext)).rstrip(". ")
        name = (stem or FALLBACK_NAME) + ext
    return name


def numbered_name(name: str, number: int) -> str:
    """Collision variant of a name: ("a.txt", 0) -> "a.txt"; ("a.txt", 2) -> "a (2).txt"."""
    if number == 0:
        return name
    stem, ext = os.path.splitext(name)
    return f"{stem} ({number}){ext}"
