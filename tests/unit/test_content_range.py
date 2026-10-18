"""Strict parsing of the Content-Range header."""

import pytest

from sdm.engine.http_download import parse_content_range


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("bytes 100-299999/300000", (100, 299999, 300000)),
        ("  bytes 0-0/1  ", (0, 0, 1)),
        ("bytes */300000", None),  # unknown range (what 416 replies carry)
        ("bytes 100-50/300000", None),  # first after last
        ("bytes 0-300000/300000", None),  # last byte past the end
        ("bytes 0-99/*", None),  # unknown total: can't verify a resume
        ("bytes -1-99/100", None),
        ("bytes 0-99/100, 200-299/300", None),
        ("items 0-99/100", None),
        ("bytes ０-99/100", None),  # non-ASCII digits
        ("", None),
        (None, None),
    ],
)
def test_parse_content_range(value, expected):
    assert parse_content_range(value) == expected
