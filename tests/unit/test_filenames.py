"""Filename extraction, Windows sanitization and collision numbering."""

import pytest

from sdm.core.filenames import (
    filename_from_content_disposition,
    filename_from_url,
    numbered_name,
    sanitize_filename,
)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ('attachment; filename="report.pdf"', "report.pdf"),
        ("attachment; filename=report.pdf", "report.pdf"),
        ('attachment; filename="say \\"hi\\".txt"', 'say "hi".txt'),
        ("attachment; filename*=UTF-8''%E2%82%AC%20rates.pdf", "€ rates.pdf"),
        ("attachment; filename=\"plain.pdf\"; filename*=UTF-8''r%C3%A9sum%C3%A9.pdf", "résumé.pdf"),
        ("attachment; filename*=ISO-8859-1''caf%E9.txt", "café.txt"),
        ("inline", None),
        ("", None),
        (None, None),
    ],
)
def test_content_disposition(header, expected):
    assert filename_from_content_disposition(header) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.com/files/setup.exe", "setup.exe"),
        ("https://example.com/files/my%20file.zip?x=1#y", "my file.zip"),
        ("https://example.com/files/", None),
        ("https://example.com", None),
    ],
)
def test_filename_from_url(url, expected):
    assert filename_from_url(url) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("report.pdf", "report.pdf"),
        ("../../evil.exe", "evil.exe"),
        ("..\\..\\Windows\\evil.exe", "evil.exe"),
        ("C:\\Windows\\System32\\x.dll", "x.dll"),
        ('a<b>c:d"e|f?g*h.txt', "a_b_c_d_e_f_g_h.txt"),
        ("tab\there\x00.txt", "tab_here_.txt"),
        ("invoice\u202etxt.exe", "invoicetxt.exe"),
        ("name.txt. . ", "name.txt"),
        ("  spaced.txt  ", "spaced.txt"),
        ("CON", "_CON"),
        ("con.txt", "_con.txt"),
        ("LPT9.tar.gz", "_LPT9.tar.gz"),
        ("CONSOLE.txt", "CONSOLE.txt"),
        ("..", "download"),
        ("", "download"),
        (None, "download"),
    ],
)
def test_sanitize(raw, expected):
    assert sanitize_filename(raw) == expected


def test_long_names_are_shortened_keeping_the_extension():
    name = sanitize_filename("x" * 300 + ".zip", max_length=50)
    assert name.endswith(".zip")
    assert len(name) == 50


def test_length_is_measured_in_utf16_units():
    name = sanitize_filename("😀" * 40 + ".txt", max_length=20)
    assert name.endswith(".txt")
    assert len(name.encode("utf-16-le")) // 2 <= 20


@pytest.mark.parametrize(
    ("name", "number", "expected"),
    [
        ("a.txt", 0, "a.txt"),
        ("a.txt", 1, "a (1).txt"),
        ("archive.tar.gz", 2, "archive.tar (2).gz"),
        ("README", 3, "README (3)"),
    ],
)
def test_numbered_name(name, number, expected):
    assert numbered_name(name, number) == expected
