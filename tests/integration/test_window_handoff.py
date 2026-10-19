"""A link from the browser opens the Add URL dialog, filled in, for the user to confirm (M7)."""

import pytest
from PySide6.QtWidgets import QDialog

from sdm.bridge.pipe import send_request
from sdm.bridge.protocol import DownloadRequest
from sdm.core.downloads import DownloadState
from sdm.ui.handoff import HandoffReceiver
from sdm.ui.main_window import MainWindow


@pytest.fixture
def window(qtbot, make_controller, tmp_path):
    window = MainWindow(make_controller(start=False), default_folder=tmp_path)
    window.confirm_quit = lambda active: True
    qtbot.addWidget(window)
    window.show()
    return window


def test_a_handoff_opens_the_dialog_filled_in(window, tmp_path):
    window.receive_handoff("https://example.com/a.zip")
    dialog = window.handoff_dialog
    assert dialog is not None and dialog.isVisible()
    assert dialog.url_edit.text() == "https://example.com/a.zip"
    assert dialog.folder_edit.text() == str(tmp_path)
    assert not dialog.local_network_check.isChecked()  # never pre-approved by the browser
    assert window.controller.model.records() == []  # nothing is added until the user agrees


def test_confirming_adds_the_download(window):
    window.receive_handoff("https://example.com/a.zip")
    dialog = window.handoff_dialog
    dialog.start_check.setChecked(False)  # keep the test offline
    dialog.accept()
    records = window.controller.model.records()
    assert [r.url for r in records] == ["https://example.com/a.zip"]
    assert records[0].state == DownloadState.PAUSED
    assert window.handoff_dialog is None


def test_cancelling_adds_nothing(window):
    window.receive_handoff("https://example.com/a.zip")
    window.handoff_dialog.reject()
    assert window.controller.model.records() == []
    assert window.handoff_dialog is None


def test_several_handoffs_wait_their_turn(window):
    window.receive_handoff("https://example.com/1.zip")
    window.receive_handoff("https://example.com/2.zip")
    first = window.handoff_dialog
    assert first.url_edit.text().endswith("1.zip")
    first.reject()
    assert window.handoff_dialog is not first
    assert window.handoff_dialog.url_edit.text().endswith("2.zip")


def test_the_url_is_checked_again_when_confirmed(window):
    window.receive_handoff("https://example.com/a.zip")
    dialog = window.handoff_dialog
    dialog.url_edit.setText("file:///C:/Windows/win.ini")  # edited (or forged) on the way
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert window.handoff_dialog is dialog  # still open, showing the error
    assert window.controller.model.records() == []


def test_a_pipe_handoff_reaches_the_window(qtbot, window, tmp_path):
    from sdm.bridge.pipe import BridgeListener, load_or_create_key, pipe_address

    receiver = HandoffReceiver()
    receiver.received.connect(window.receive_handoff)
    window.handoff_closed.connect(receiver.done)
    key_path = tmp_path / "bridge.key"
    key = load_or_create_key(key_path)
    listener = BridgeListener(key, pipe_address(key_path), receiver.offer)
    listener.start()
    try:
        reply = send_request(
            DownloadRequest("https://example.com/b.zip"), key=key, address=pipe_address(key_path)
        )
        assert reply == {"ok": True}
        qtbot.waitUntil(lambda: window.handoff_dialog is not None, timeout=5000)
        assert window.handoff_dialog.url_edit.text() == "https://example.com/b.zip"
    finally:
        listener.close()


def test_too_many_waiting_handoffs_are_refused(window):
    receiver = HandoffReceiver()
    receiver.received.connect(window.receive_handoff)
    window.handoff_closed.connect(receiver.done)
    request = DownloadRequest("https://example.com/a.zip")
    results = [receiver.offer(request) for _ in range(HandoffReceiver.MAX_PENDING + 1)]
    assert results == [True] * HandoffReceiver.MAX_PENDING + [False]
    window.handoff_dialog.reject()  # one dialog closes, so one more fits
    assert receiver.offer(request) is True


# ----- M8: what the browser said -----

CAPTURED = DownloadRequest(
    "https://example.com/dl?id=9",
    referrer="https://example.com/files/page?session=secret",
    filename="report.pdf",
    size=12_673_227,
    mime="application/pdf",
    source="capture",
)


def test_the_dialog_says_what_the_browser_knew(window):
    window.receive_handoff(CAPTURED)
    label = window.handoff_dialog.browser_label
    assert not label.isHidden()
    text = label.text()
    assert text.startswith("Captured from Chrome: report.pdf")
    assert "12.1 MB" in text and "application/pdf" in text
    assert "from a page on example.com" in text
    assert "secret" not in text  # only the page's host is shown, never its address


def test_confirming_keeps_the_browsers_hints(window):
    window.receive_handoff(CAPTURED)
    dialog = window.handoff_dialog
    dialog.start_check.setChecked(False)
    dialog.accept()
    (record,) = window.controller.model.records()
    stored = window.controller.store.get(record.id)
    assert stored.referrer == CAPTURED.referrer
    assert stored.suggested_name == "report.pdf"
    assert stored.category == "Documents"


def test_editing_the_address_drops_the_hints(window):
    window.receive_handoff(CAPTURED)
    dialog = window.handoff_dialog
    dialog.url_edit.setText("https://other.example/x.zip")
    dialog.start_check.setChecked(False)
    dialog.accept()
    (record,) = window.controller.model.records()
    assert window.controller.store.get(record.id).context() is None


def test_a_file_name_is_shown_as_text_never_as_html(window):
    from PySide6.QtCore import Qt

    window.receive_handoff(DownloadRequest("https://example.com/a", filename="<img src=x>.zip"))
    label = window.handoff_dialog.browser_label
    assert label.textFormat() == Qt.TextFormat.PlainText
    assert "<img src=x>.zip" in label.text()


def test_a_plain_link_from_the_menu_says_where_it_came_from(window):
    window.receive_handoff(DownloadRequest("https://example.com/a.zip",
                                           referrer="https://example.com/"))  # fmt: skip
    assert window.handoff_dialog.browser_label.text() == "From Chrome: from a page on example.com"
