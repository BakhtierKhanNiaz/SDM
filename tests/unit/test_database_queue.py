"""History schema version 4: queue positions, categories, retries, settings (M6)."""

import pytest

from sdm.core.downloads import DownloadState
from sdm.scheduler.persist import load_queue_settings, save_queue_settings
from sdm.scheduler.queue import QueueSettings, Schedule
from sdm.storage.database import SCHEMA_VERSION, DownloadStore

URL = "https://example.com/a.zip"


@pytest.fixture
def store(tmp_path):
    store = DownloadStore(tmp_path / "sdm.db")
    yield store
    store.close()


def test_new_entries_go_to_the_end_of_the_queue(store, tmp_path):
    assert SCHEMA_VERSION >= 4
    ids = [store.add(URL, str(tmp_path)).id for _ in range(3)]
    assert [store.get(i).queue_position for i in ids] == [1, 2, 3]


def test_add_without_starting(store, tmp_path):
    record = store.add(URL, str(tmp_path), start=False, category="Compressed")
    assert record.state == DownloadState.PAUSED
    assert record.category == "Compressed"


def test_reordering_keeps_the_same_positions(store, tmp_path):
    a, b, c = (store.add(URL, str(tmp_path)).id for _ in range(3))
    store.set_positions([c, a, b])
    assert [r.id for r in store.list_all()] == [c, a, b]  # listed in queue order
    assert sorted(store.get(i).queue_position for i in (a, b, c)) == [1, 2, 3]


def test_finishing_clears_start_now_and_the_retry_time(store, tmp_path):
    download_id = store.add(URL, str(tmp_path)).id
    store.set_forced(download_id, True)
    store.set_retry(download_id, 2, "2026-10-19T12:00:00+00:00")
    store.mark_downloading(download_id)
    store.mark_completed(download_id, path=str(tmp_path / "a.zip"), size=1, verified_complete=True)
    record = store.get(download_id)
    assert (record.forced, record.retry_at, record.retry_count) == (False, None, 2)


def test_queue_settings_round_trip(store):
    assert load_queue_settings(store) == QueueSettings()  # defaults on a new history
    settings = QueueSettings(limit=5, schedule=Schedule.from_json(None), category_subfolders=True)
    save_queue_settings(store, settings)
    assert load_queue_settings(store) == settings


def test_bad_saved_settings_fall_back_to_defaults(store):
    store.set_setting("queue.limit", "lots")
    store.set_setting("queue.schedule", "{broken")
    assert load_queue_settings(store) == QueueSettings()


def test_upgrade_labels_existing_downloads_by_file_name(tmp_path):
    import sqlite3
    from contextlib import closing

    from sdm.storage import database

    path = tmp_path / "old.db"
    with closing(sqlite3.connect(path)) as conn:
        for script in database._MIGRATIONS[:3]:  # a version-3 history, as M5 left it
            conn.executescript(script)
        conn.execute("PRAGMA user_version = 3")
        conn.execute(
            "INSERT INTO downloads (url, folder, state, file_name, created_at, updated_at)"
            " VALUES ('https://example.com/a.zip', 'D:\\', 'completed', 'a (1).zip', 't', 't')"
        )
        conn.commit()

    store = DownloadStore(path)
    try:
        assert store.list_all()[0].category == "Compressed"
    finally:
        store.close()
