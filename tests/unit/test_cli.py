"""The sdm-get command line."""

from pathlib import Path

import pytest

from sdm import cli
from sdm.cli import format_size, main
from sdm.engine.models import DownloadResult


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


@pytest.mark.parametrize("verified", [True, False], ids=["size-known", "size-unknown"])
def test_warns_only_when_completeness_cant_be_confirmed(tmp_path, capsys, monkeypatch, verified):
    async def fake_download(url, dest, **kwargs):  # no network: the engine is replaced
        return DownloadResult(
            path=Path(dest) / "stream.bin",
            size=2048,
            final_url=url,
            content_type=None,
            verified_complete=verified,
        )

    monkeypatch.setattr(cli, "download", fake_download)
    assert main(["https://example.com/stream.bin", "--dest", str(tmp_path)]) == 0
    out, err = capsys.readouterr()
    assert "Saved" in out and "stream.bin" in out
    assert ("can't confirm that the whole file arrived" in err) is not verified
