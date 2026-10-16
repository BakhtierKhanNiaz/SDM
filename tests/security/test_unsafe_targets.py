"""Attempts to make SDM fetch from places it must not, or write outside the download folder."""

import pytest

from sdm.cli import main
from sdm.core.errors import BlockedDestinationError, InvalidURLError, SDMError
from sdm.engine.policy import NetworkPolicy


class OnlyLiteralLoopback(NetworkPolicy):
    """Lets the test server's 127.0.0.1 literal through but blocks names resolving to loopback,
    so the resolver check can be exercised on a redirect hop."""

    def check_ip(self, ip: str, host: str) -> None:
        if host == "127.0.0.1":
            return
        super().check_ip(ip, host)


def test_default_policy_blocks_this_computer_by_ip(mock_server, fetch, tmp_path):
    mock_server.add("/f", mock_server.file(b"secret"))
    with pytest.raises(BlockedDestinationError, match="this computer"):
        fetch(mock_server.url("/f"), policy=NetworkPolicy())
    assert mock_server.hits["/f"] == 0
    assert list(tmp_path.iterdir()) == []


def test_default_policy_blocks_this_computer_by_name(mock_server, fetch):
    mock_server.add("/f", mock_server.file(b"secret"))
    with pytest.raises(BlockedDestinationError, match="localhost points to this computer"):
        fetch(f"http://localhost:{mock_server.port}/f", policy=NetworkPolicy())
    assert mock_server.hits["/f"] == 0


@pytest.mark.parametrize("host", ["127.1", "2130706433", "0x7f000001", "127.000.000.001"])
def test_disguised_spellings_of_this_computer_never_reach_it(mock_server, fetch, host):
    # Python's ipaddress rejects these spellings, so they take the hostname path. Observed:
    # aiohttp refuses the first, second and fourth as non-canonical IPv4; Windows DNS can't
    # resolve the hex form. Whatever stops them, no request may reach the server.
    mock_server.add("/f", mock_server.file(b"secret"))
    with pytest.raises(SDMError):
        fetch(f"http://{host}:{mock_server.port}/f", policy=NetworkPolicy())
    assert mock_server.hits["/f"] == 0


def test_redirect_to_a_name_resolving_to_this_computer_is_blocked(mock_server, fetch):
    mock_server.add("/go", mock_server.redirect(f"http://localhost:{mock_server.port}/target"))
    mock_server.add("/target", mock_server.file(b"secret"))
    with pytest.raises(BlockedDestinationError, match="localhost points to this computer"):
        fetch(mock_server.url("/go"), policy=OnlyLiteralLoopback())
    assert mock_server.hits["/target"] == 0


@pytest.mark.parametrize(
    ("location", "error", "message"),
    [
        ("http://169.254.169.254/latest/meta-data/", BlockedDestinationError, "special network"),
        ("http://10.0.0.1/admin", BlockedDestinationError, "local or private network"),
        ("file:///C:/Windows/win.ini", InvalidURLError, "redirected to an address SDM refuses"),
        ("ftp://example.com/x", InvalidURLError, "redirected to an address SDM refuses"),
        ("http://user:pw@example.com/x", InvalidURLError, "redirected to an address SDM refuses"),
    ],
)
def test_redirects_to_unsafe_targets_are_refused(
    mock_server, fetch, tmp_path, location, error, message
):
    mock_server.add("/go", mock_server.redirect(location))
    with pytest.raises(error, match=message):
        fetch(mock_server.url("/go"))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("disposition", "expected"),
    [
        # Inside quotes a backslash escapes the next character (RFC 9110), so "\\" is a
        # real backslash, and a lone "\" just disappears.
        ('attachment; filename="..\\\\..\\\\Windows\\\\evil.exe"', "evil.exe"),
        ('attachment; filename="..\\..\\..\\Windows\\evil.exe"', "......Windowsevil.exe"),
        ("attachment; filename=..\\..\\Windows\\evil.exe", "evil.exe"),
        ('attachment; filename="../../../etc/passwd"', "passwd"),
        ("attachment; filename*=UTF-8''..%2F..%2Fevil.bat", "evil.bat"),
        ('attachment; filename="CON"', "_CON"),
        ("attachment; filename*=UTF-8''invoice%E2%80%AEtxt.exe", "invoicetxt.exe"),
    ],
)
def test_hostile_filenames_stay_inside_the_download_folder(
    mock_server, fetch, tmp_path, disposition, expected
):
    dest = tmp_path / "downloads"
    dest.mkdir()
    mock_server.add("/f", mock_server.file(b"data", headers={"Content-Disposition": disposition}))

    result = fetch(mock_server.url("/f"), dest=dest)

    assert result.path == dest / expected
    assert [p.name for p in tmp_path.iterdir()] == ["downloads"]


def test_cli_refuses_to_download_from_this_computer(mock_server, tmp_path, capsys):
    mock_server.add("/secret.txt", mock_server.file(b"secret"))
    assert main([mock_server.url("/secret.txt"), "--dest", str(tmp_path)]) == 1
    assert "this computer" in capsys.readouterr().err
    assert mock_server.hits["/secret.txt"] == 0
    assert list(tmp_path.iterdir()) == []
