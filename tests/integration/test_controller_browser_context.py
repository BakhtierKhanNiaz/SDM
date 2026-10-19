"""The browser's hints survive the history and reach the server, also after a restart (M8)."""

import os
import sqlite3
from contextlib import closing

from sdm.core.downloads import BrowserContext, DownloadState
from sdm.storage import database
from sdm.storage.database import DownloadStore

DATA = os.urandom(30_000)


def wait_for_state(qtbot, controller, download_id, state, timeout=15_000):
    qtbot.waitUntil(lambda: controller.store.get(download_id).state == state, timeout=timeout)


def test_the_history_keeps_the_hints(tmp_path):
    store = DownloadStore(tmp_path / "sdm.db")
    try:
        context = BrowserContext(referrer="https://example.com/p", suggested_name="a.zip")
        record = store.add("https://example.com/dl", str(tmp_path), context=context)
        assert store.get(record.id).context() == context
        plain = store.add("https://example.com/b.zip", str(tmp_path))
        assert store.get(plain.id).context() is None
    finally:
        store.close()


def test_upgrading_to_version_5_keeps_old_entries(tmp_path):
    path = tmp_path / "old.db"
    with closing(sqlite3.connect(path)) as conn:
        for script in database._MIGRATIONS[:4]:  # a version-4 history, as M6 left it
            conn.executescript(script)
        conn.execute("PRAGMA user_version = 4")
        conn.execute(
            "INSERT INTO downloads (url, folder, state, file_name, created_at, updated_at)"
            " VALUES ('https://example.com/a.zip', 'D:\\', 'completed', 'a.zip', 't', 't')"
        )
        conn.commit()
    store = DownloadStore(path)
    try:
        (record,) = store.list_all()
        assert record.file_name == "a.zip"
        assert record.context() is None
        assert database.SCHEMA_VERSION >= 5
    finally:
        store.close()


def test_a_browser_download_sends_its_referer_through_the_window_code(
    qtbot, make_controller, mock_server, tmp_path
):
    mock_server.add("/download", mock_server.file(DATA))
    page = mock_server.url("/page.html?id=3")
    controller = make_controller()
    record = controller.add(
        mock_server.url("/download"),
        tmp_path,
        context=BrowserContext(referrer=page, suggested_name="Report.pdf"),
    )
    assert record.category == "Documents"  # from the browser's name, not the URL
    wait_for_state(qtbot, controller, record.id, DownloadState.COMPLETED)
    done = controller.store.get(record.id)
    assert done.file_name == "Report.pdf"
    assert (tmp_path / "Report.pdf").read_bytes() == DATA
    assert [h.get("Referer") for h in mock_server.requests] == [page]


def test_a_resume_after_a_restart_sends_the_same_referer(
    qtbot, make_controller, mock_server, tmp_path
):
    data = os.urandom(200_000)
    mock_server.add("/a.bin", mock_server.ranged(data, etag='"v1"', stall_at=(60_000, 30)),
                    mock_server.ranged(data, etag='"v1"'))  # fmt: skip
    page = mock_server.url("/page.html")
    controller = make_controller()
    record = controller.add(mock_server.url("/a.bin"), tmp_path,
                            context=BrowserContext(referrer=page))  # fmt: skip
    qtbot.waitUntil(lambda: controller.store.get(record.id).part_path is not None, timeout=10_000)
    qtbot.waitUntil(lambda: controller.model.record(record.id).received_bytes > 0, timeout=10_000)
    controller.pause(record.id)
    wait_for_state(qtbot, controller, record.id, DownloadState.PAUSED)
    controller.shutdown()

    reopened = make_controller(start=True)  # the same history file, as after a restart
    reopened.resume(record.id)
    wait_for_state(qtbot, reopened, record.id, DownloadState.COMPLETED)
    assert (tmp_path / "a.bin").read_bytes() == data
    assert mock_server.requests[-1].get("Range", "").startswith("bytes=")
    assert {h.get("Referer") for h in mock_server.requests} == {page}
