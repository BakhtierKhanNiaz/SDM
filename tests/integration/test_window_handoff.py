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
