"""The download list's table model and what each cell says."""

from dataclasses import replace

from PySide6.QtCore import Qt

from sdm.core.downloads import DownloadRecord, DownloadState
from sdm.ui.controller import summarize
from sdm.ui.download_model import (
    NAME,
    PROGRESS,
    SIZE,
    SPEED,
    STATUS,
    TIME_LEFT,
    UNCONFIRMED,
    DownloadTableModel,
    cell_text,
)

MB = 1024 * 1024
BASE = DownloadRecord(
    id=1,
    url="https://example.com/files/a.zip?token=secret",
    folder="D:\\Downloads",
    allow_local_network=False,
    state=DownloadState.QUEUED,
    file_name=None,
    path=None,
    total_bytes=None,
    received_bytes=0,
    verified_complete=None,
    error=None,
    created_at="2026-10-18T10:00:00+00:00",
    updated_at="2026-10-18T10:00:00+00:00",
    finished_at=None,
)


def rec(**changes) -> DownloadRecord:
    return replace(BASE, **changes)


def row(record, speed=None, time_left=None):
    return [
        cell_text(record, c, speed, time_left)
        for c in (NAME, SIZE, PROGRESS, SPEED, TIME_LEFT, STATUS)
    ]


def test_queued_row_hides_the_token_in_the_url():
    assert row(rec()) == ["https://example.com/files/a.zip?<redacted>", "", "", "", "", "Queued"]


def test_downloading_with_a_known_size():
    record = rec(
        state=DownloadState.DOWNLOADING,
        file_name="a.zip",
        total_bytes=4 * MB,
        received_bytes=1 * MB,
    )
    assert row(record, speed=512 * 1024, time_left=6) == [
        "a.zip",
        "4.0 MB",
        "25%",
        "512.0 KB/s",
        "6 s",
        "Downloading",
    ]


def test_downloading_with_an_unknown_size():
    record = rec(state=DownloadState.DOWNLOADING, file_name="stream.bin", received_bytes=1536)
    assert row(record, speed=1024) == [
        "stream.bin",
        "Unknown",
        "1.5 KB",
        "1.0 KB/s",
        "",
        "Downloading",
    ]


def test_finished_rows_show_no_speed():
    record = rec(
        state=DownloadState.COMPLETED,
        file_name="a.zip",
        total_bytes=MB,
        received_bytes=MB,
        verified_complete=True,
    )
    assert row(record, speed=1000, time_left=1) == ["a.zip", "1.0 MB", "100%", "", "", "Completed"]


def test_completed_without_a_size_says_so(qapp):
    record = rec(
        state=DownloadState.COMPLETED,
        file_name="s.bin",
        received_bytes=3 * MB,
        verified_complete=False,
    )
    assert cell_text(record, STATUS) == "Completed (size unconfirmed)"
    model = DownloadTableModel()
    model.set_records([record])
    assert model.data(model.index(0, STATUS), Qt.ItemDataRole.ToolTipRole) == UNCONFIRMED


def test_failed_row_shows_the_error_as_a_tooltip(qapp):
    model = DownloadTableModel()
    model.set_records([rec(state=DownloadState.FAILED, error="The file was not found.")])
    assert model.data(model.index(0, STATUS)) == "Failed"
    assert (
        model.data(model.index(0, STATUS), Qt.ItemDataRole.ToolTipRole) == "The file was not found."
    )


def test_model_insert_update_live_and_remove(qtmodeltester):
    model = DownloadTableModel()
    model.set_records([rec(id=1), rec(id=2, state=DownloadState.COMPLETED, received_bytes=5)])
    qtmodeltester.check(model)  # pytest-qt's consistency checks for Qt models

    model.upsert(rec(id=3))
    assert model.rowCount() == 3
    model.upsert(rec(id=1, state=DownloadState.DOWNLOADING))
    assert model.record(1).state == DownloadState.DOWNLOADING
    model.set_live(1, 2 * MB, 4 * MB, speed=MB, time_left=2.0)
    assert model.data(model.index(0, PROGRESS)) == "50%"
    assert model.data(model.index(0, TIME_LEFT)) == "2 s"
    model.upsert(rec(id=1, state=DownloadState.CANCELLED, received_bytes=2 * MB))
    assert model.data(model.index(0, SPEED)) == ""  # live numbers are cleared when it stops
    model.remove(2)
    assert [r.id for r in model.records()] == [1, 3]
    qtmodeltester.check(model)


def test_summary_line():
    assert summarize([]) == "No downloads yet"
    records = [
        rec(id=1, state=DownloadState.DOWNLOADING),
        rec(id=2, state=DownloadState.QUEUED),
        rec(id=3, state=DownloadState.COMPLETED),
        rec(id=4, state=DownloadState.FAILED),
    ]
    assert summarize(records) == "1 downloading, 1 waiting · 1 completed"
    assert summarize(records[2:]) == "Ready · 1 completed"


def test_size_is_blank_when_the_server_never_answered():
    failed = rec(state=DownloadState.FAILED, error="Could not connect to example.com.")
    assert cell_text(failed, SIZE) == ""
    answered = rec(state=DownloadState.FAILED, file_name="a.zip", error="interrupted")
    assert cell_text(answered, SIZE) == "Unknown"
