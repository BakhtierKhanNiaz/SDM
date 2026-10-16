"""Parsing the Retry-After header."""

import email.utils
from datetime import UTC, datetime, timedelta

import pytest

from sdm.engine.http_download import parse_retry_after


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("5", 5.0),
        (" 120 ", 120.0),
        ("Wed, 21 Oct 2015 07:28:00 GMT", 0.0),  # a date in the past means "now"
        ("soon", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_retry_after(value, expected):
    assert parse_retry_after(value) == expected


def test_parse_retry_after_future_date():
    future = email.utils.format_datetime(datetime.now(UTC) + timedelta(seconds=30), usegmt=True)
    assert 25 <= parse_retry_after(future) <= 30
