"""Regression tests for the bugs the M10 fuzz tests found, one plain example each."""

import asyncio

import pytest

from sdm.bridge.protocol import ProtocolError, parse_request
from sdm.core.errors import InvalidURLError, SDMError
from sdm.core.filenames import sanitize_filename
from sdm.core.referrer import check_redirect
from sdm.core.urls import validate_url

URL = "https://example.com/a.zip"


def test_a_list_as_source_is_refused_not_a_crash():
    # Was: TypeError (unhashable list) inside the host and the app's listener.
    with pytest.raises(ProtocolError):
        parse_request({"version": 2, "type": "download", "url": URL, "source": []})


def test_a_file_name_with_a_lone_surrogate():
    # JSON allows "\ud800"; Windows file names can't hold it. Was: UnicodeEncodeError.
    with pytest.raises(ProtocolError):
        parse_request({"version": 2, "type": "download", "url": URL, "filename": "a\ud800.zip"})
    assert sanitize_filename("report\udfff.pdf") == "report_.pdf"


@pytest.mark.parametrize("url", ["http://[", "https://[::1", "http://]x["])
def test_a_malformed_server_name_is_an_invalid_url(url):
    # Was: ValueError ("Invalid IPv6 URL") from urlsplit, e.g. while typing in Add URL.
    with pytest.raises(InvalidURLError):
        validate_url(url)


def test_add_url_survives_typing_a_malformed_address(qtbot, tmp_path):
    from sdm.ui.add_url_dialog import AddUrlDialog

    dialog = AddUrlDialog(default_folder=tmp_path, previous_downloads=lambda url: [])
    qtbot.addWidget(dialog)
    dialog.url_edit.setText("http://[")  # runs the live check on every keystroke
    dialog.accept()
    assert "malformed" in dialog.error_label.text()


def test_a_redirect_to_a_malformed_address_is_refused_cleanly():
    # Was: ValueError from the https-to-http check, before validate_url could refuse it.
    assert check_redirect("https://a.example/x", "http://[") is False
    assert check_redirect("http://a.example/x", "http://[") is True

    from sdm.engine import http_download
    from sdm.engine.models import DownloadSettings
    from sdm.engine.policy import NetworkPolicy

    class Response:
        status = 302
        headers = {"Location": "http://["}

        def release(self):
            pass

    class Session:
        async def get(self, url, allow_redirects, headers):
            return Response()

    with pytest.raises(SDMError):
        asyncio.run(
            http_download._get_following_redirects(
                Session(), "http://a.example/x", NetworkPolicy(), DownloadSettings()
            )
        )
