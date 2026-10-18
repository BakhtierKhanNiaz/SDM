"""The Add URL dialog."""

from dataclasses import replace

import pytest
from PySide6.QtWidgets import QDialog

from sdm.core.downloads import DownloadRecord, DownloadState
from sdm.ui.add_url_dialog import AddUrlDialog

URL = "https://example.com/files/a.zip"


@pytest.fixture
def previous():
    return {}  # url -> earlier completed downloads, filled in by each test


@pytest.fixture
def dialog(qtbot, tmp_path, previous):
    dialog = AddUrlDialog(
        default_folder=tmp_path, previous_downloads=lambda url: previous.get(url, [])
    )
    qtbot.addWidget(dialog)
    return dialog


def completed(file_name: str) -> DownloadRecord:
    return DownloadRecord(
        id=7,
        url=URL,
        folder="D:\\Downloads",
        allow_local_network=False,
        state=DownloadState.COMPLETED,
        file_name=file_name,
        path=f"D:\\Downloads\\{file_name}",
        total_bytes=10,
        received_bytes=10,
        verified_complete=True,
        error=None,
        created_at="2026-10-18T10:00:00+00:00",
        updated_at="2026-10-18T10:00:05+00:00",
        finished_at="2026-10-18T10:00:05+00:00",
    )


def test_unsupported_url_is_refused_with_a_message(dialog):
    dialog.url_edit.setText("ftp://example.com/file.zip")
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert not dialog.error_label.isHidden()
    assert "Only http:// and https://" in dialog.error_label.text()


def test_missing_folder_is_refused(dialog, tmp_path):
    dialog.url_edit.setText(URL)
    dialog.folder_edit.setText(str(tmp_path / "nope"))
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "doesn't exist" in dialog.error_label.text()


def test_valid_input_is_accepted(dialog, tmp_path):
    dialog.url_edit.setText(f"  {URL}  ")
    dialog.local_network_check.setChecked(True)
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert (dialog.url, dialog.folder, dialog.allow_local_network) == (URL, tmp_path, True)


def test_warns_when_the_url_was_downloaded_before(dialog, previous):
    previous[URL] = [replace(completed("a.zip"), id=3), completed("a (1).zip")]
    dialog.url_edit.setText(URL)
    assert not dialog.warning_label.isHidden()
    text = dialog.warning_label.text()
    assert "a (1).zip" in text  # the most recent copy
    assert "nothing is overwritten" in text


def test_no_warning_for_a_new_url(dialog):
    dialog.url_edit.setText(URL)
    assert dialog.warning_label.isHidden()
