"""The sdm-get command line."""

import pytest

from sdm.cli import format_size, main


@pytest.mark.parametrize(
    ("num_bytes", "expected"),
    [(500, "500 bytes"), (1536, "1.5 KB"), (5 * 1024**2, "5.0 MB"), (3 * 1024**4, "3072.0 GB")],
)
def test_format_size(num_bytes, expected):
    assert format_size(num_bytes) == expected


def test_unsupported_url_gives_an_error_and_exit_code_1(tmp_path, capsys):
    assert main(["ftp://example.com/file", "--dest", str(tmp_path)]) == 1
    assert "Only http:// and https://" in capsys.readouterr().err


def test_missing_destination_folder(tmp_path, capsys):
    missing = tmp_path / "nope"
    assert main(["https://example.com/file", "--dest", str(missing)]) == 1
    assert "does not exist" in capsys.readouterr().err
