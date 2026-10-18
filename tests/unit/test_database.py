"""The SQLite download history."""

import sqlite3
from contextlib import closing

import pytest

from sdm.core.downloads import DownloadState
from sdm.storage.database import (
    INTERRUPTED_MESSAGE,
    SCHEMA_VERSION,
    DownloadStore,
    StorageError,
    default_database_path,
)

URL = "https://example.com/files/a.zip"
FOLDER = "D:\\Downloads"


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "SDM" / "sdm.db"


@pytest.fixture
def store(db_path):
    store = DownloadStore(db_path)
    yield store
    store.close()


def schema_version(path) -> int:
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


def test_new_database_gets_the_current_schema(store, db_path):
    assert db_path.exists()  # its folder was created too
    assert schema_version(db_path) == SCHEMA_VERSION
    assert store.recovered_from is None


def test_add_and_read_back(store):
    record = store.add(URL, FOLDER, allow_local_network=True)
    assert record.state == DownloadState.QUEUED
    assert (record.url, record.folder, record.allow_local_network) == (URL, FOLDER, True)
    assert record.received_bytes == 0
    assert record.file_name is None and record.finished_at is None
    assert store.get(record.id) == record
    assert store.list_all() == [record]


def test_full_lifecycle(store):
    download_id = store.add(URL, FOLDER).id
    store.mark_downloading(download_id)
    store.set_file_info(download_id, "a.zip", 100)
    store.set_progress(download_id, 50)
    assert store.get(download_id).received_bytes == 50

    store.mark_completed(
        download_id, path="D:\\Downloads\\a (1).zip", size=100, verified_complete=True
    )

    record = store.get(download_id)
    assert record.state == DownloadState.COMPLETED
    assert record.file_name == "a (1).zip"  # the final name, after the collision suffix
    assert (record.received_bytes, record.total_bytes) == (100, 100)
    assert record.verified_complete is True
    assert record.finished_at is not None


def test_failure_keeps_the_message(store):
    download_id = store.add(URL, FOLDER).id
    store.mark_downloading(download_id)
    store.mark_failed(download_id, "The file was not found on the server (404 Not Found).")
    record = store.get(download_id)
    assert record.state == DownloadState.FAILED
    assert "404" in record.error


def test_illegal_state_changes_are_refused(store):
    download_id = store.add(URL, FOLDER).id
    with pytest.raises(ValueError, match="can't go from"):
        store.mark_completed(download_id, path="x", size=1, verified_complete=True)
    store.mark_downloading(download_id)
    store.mark_cancelled(download_id)
    with pytest.raises(ValueError, match="can't go from"):
        store.mark_failed(download_id, "too late")
    assert store.get(download_id).state == DownloadState.CANCELLED


def test_history_survives_reopening(db_path):
    first = DownloadStore(db_path)
    download_id = first.add(URL, FOLDER).id
    first.mark_downloading(download_id)
    first.mark_completed(download_id, path="D:\\Downloads\\a.zip", size=10, verified_complete=False)
    before = first.list_all()
    first.close()

    second = DownloadStore(db_path)
    try:
        assert second.list_all() == before
    finally:
        second.close()


def test_unfinished_downloads_become_interrupted_after_a_crash(db_path):
    first = DownloadStore(db_path)
    waiting = first.add(URL, FOLDER).id
    running = first.add(URL, FOLDER).id
    first.mark_downloading(running)
    done = first.add(URL, FOLDER).id
    first.mark_downloading(done)
    first.mark_completed(done, path="D:\\Downloads\\a.zip", size=1, verified_complete=True)
    first.close()  # as if SDM crashed here

    second = DownloadStore(db_path)
    try:
        assert second.mark_interrupted_on_startup() == 2
        for download_id in (waiting, running):
            record = second.get(download_id)
            assert record.state == DownloadState.INTERRUPTED
            assert record.error == INTERRUPTED_MESSAGE
        assert second.get(done).state == DownloadState.COMPLETED
    finally:
        second.close()


def test_completed_with_url(store):
    first = store.add(URL, FOLDER).id
    store.mark_downloading(first)
    store.mark_completed(first, path="D:\\Downloads\\a.zip", size=1, verified_complete=True)
    store.add(URL, FOLDER)  # queued, not completed
    store.add("https://example.com/other.zip", FOLDER)
    assert [r.id for r in store.completed_with_url(URL)] == [first]


def test_remove_deletes_the_entry_but_not_the_file(store, tmp_path):
    saved = tmp_path / "a.zip"
    saved.write_bytes(b"data")
    download_id = store.add(URL, str(tmp_path)).id
    store.mark_downloading(download_id)
    store.mark_completed(download_id, path=str(saved), size=4, verified_complete=True)

    store.remove(download_id)

    assert store.get(download_id) is None
    assert saved.read_bytes() == b"data"


def test_active_downloads_cannot_be_removed(store):
    download_id = store.add(URL, FOLDER).id
    with pytest.raises(ValueError, match="Cancel the download"):
        store.remove(download_id)


def test_urls_are_stored_as_data_not_sql(store):
    nasty = "https://example.com/a.zip?x=1'); DROP TABLE downloads; --"
    record = store.add(nasty, FOLDER)
    assert store.get(record.id).url == nasty
    assert len(store.list_all()) == 1  # the table is still there


def test_corrupted_database_is_set_aside_and_replaced(db_path):
    db_path.parent.mkdir(parents=True)
    garbage = b"this is not a SQLite database " * 200
    db_path.write_bytes(garbage)

    store = DownloadStore(db_path)
    try:
        assert store.recovered_from is not None
        assert store.recovered_from.name.startswith("sdm.db.corrupt-")
        assert store.recovered_from.read_bytes() == garbage  # kept, not deleted
        assert store.list_all() == []
        store.add(URL, FOLDER)  # the fresh database works
    finally:
        store.close()


def test_database_from_a_newer_sdm_is_refused_and_left_alone(db_path):
    db_path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 5}")

    with pytest.raises(StorageError, match="newer version of SDM"):
        DownloadStore(db_path)
    assert schema_version(db_path) == SCHEMA_VERSION + 5
    assert not list(db_path.parent.glob("*.corrupt-*"))


def test_default_path_is_under_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert default_database_path() == tmp_path / "SDM" / "sdm.db"
