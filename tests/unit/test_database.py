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


# ----- M4: schema version 2, partial files, pause and resume -----


def test_upgrade_from_version_1_keeps_history(db_path):
    from sdm.storage import database

    db_path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.executescript(database._MIGRATIONS[0])
        conn.execute("PRAGMA user_version = 1")
        conn.execute(
            "INSERT INTO downloads (id, url, folder, state, file_name, received_bytes,"
            " created_at, updated_at) VALUES (7, ?, ?, 'completed', 'a.zip', 10, 't', 't')",
            (URL, FOLDER),
        )
        conn.commit()

    store = DownloadStore(db_path)
    try:
        assert schema_version(db_path) == SCHEMA_VERSION  # upgraded all the way
        old = store.get(7)
        assert (old.state, old.file_name, old.received_bytes) == ("completed", "a.zip", 10)
        assert (old.part_path, old.etag, old.resumable) == (None, None, False)
        assert store.add(URL, FOLDER).id == 8  # ids are never reused
        store.mark_downloading(8)
        store.mark_paused(8)  # the new state is accepted
    finally:
        store.close()


def partial_for(folder, name="a.zip"):
    from pathlib import Path

    from sdm.core.downloads import PartialDownload

    return PartialDownload(Path(folder) / f"{name}.sdmpart", name, 1000, '"v1"', None, True)


def test_partial_file_round_trip_and_pause_resume(store, tmp_path):
    download_id = store.add(URL, str(tmp_path)).id
    store.mark_downloading(download_id)
    partial = partial_for(tmp_path)
    store.set_partial(download_id, partial)
    store.set_progress(download_id, 400)
    store.mark_paused(download_id)

    record = store.get(download_id)
    assert record.state == DownloadState.PAUSED
    assert record.partial() == partial
    assert record.received_bytes == 400

    store.mark_queued(download_id)  # resume
    record = store.get(download_id)
    assert record.state == DownloadState.QUEUED
    assert record.finished_at is None and record.error is None
    assert record.partial() == partial  # still known, for the resume


@pytest.mark.parametrize("kept", [True, False])
def test_failure_keeps_the_partial_only_if_it_was_kept(store, tmp_path, kept):
    download_id = store.add(URL, str(tmp_path)).id
    store.mark_downloading(download_id)
    store.set_partial(download_id, partial_for(tmp_path))
    store.mark_failed(download_id, "interrupted", partial_kept=kept)
    assert (store.get(download_id).partial() is not None) is kept


def test_cancel_and_complete_forget_the_partial(store, tmp_path):
    first = store.add(URL, str(tmp_path)).id
    store.mark_downloading(first)
    store.set_partial(first, partial_for(tmp_path))
    store.mark_paused(first)
    store.mark_cancelled(first)
    assert store.get(first).partial() is None

    second = store.add(URL, str(tmp_path)).id
    store.mark_downloading(second)
    store.set_partial(second, partial_for(tmp_path, "b.zip"))
    store.mark_completed(second, path=str(tmp_path / "b.zip"), size=1000, verified_complete=True)
    assert store.get(second).partial() is None


def test_interrupted_entries_keep_their_partial_for_resuming(db_path, tmp_path):
    first = DownloadStore(db_path)
    download_id = first.add(URL, str(tmp_path)).id
    first.mark_downloading(download_id)
    first.set_partial(download_id, partial_for(tmp_path))
    first.close()  # crash

    second = DownloadStore(db_path)
    try:
        second.mark_interrupted_on_startup()
        record = second.get(download_id)
        assert record.state == DownloadState.INTERRUPTED
        assert record.partial() is not None
        second.mark_queued(download_id)  # interrupted entries can be resumed
    finally:
        second.close()
