"""History schema version 3: the parts map of split downloads (M5)."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from sdm.core.downloads import PartialDownload
from sdm.core.segments import Segment
from sdm.storage.database import SCHEMA_VERSION, DownloadStore

SEGMENTS = (Segment(0, 499, 500), Segment(500, 999, 120))


@pytest.fixture
def store(tmp_path):
    store = DownloadStore(tmp_path / "sdm.db")
    yield store
    store.close()


def split_partial(folder: Path) -> PartialDownload:
    return PartialDownload(folder / "a.zip.sdmpart", "a.zip", 1000, '"v1"', None, True, SEGMENTS)


def test_schema_has_the_segments_column(store, tmp_path):
    assert SCHEMA_VERSION >= 3  # added in version 3
    with closing(sqlite3.connect(tmp_path / "sdm.db")) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(downloads)")]
    assert "segments" in columns


def test_parts_map_round_trip(store, tmp_path):
    download_id = store.add("https://example.com/a.zip", str(tmp_path)).id
    store.mark_downloading(download_id)
    store.set_partial(download_id, split_partial(tmp_path))

    assert store.get(download_id).partial() == split_partial(tmp_path)


def test_damaged_parts_map_means_no_resume(store, tmp_path):
    download_id = store.add("https://example.com/a.zip", str(tmp_path)).id
    store.mark_downloading(download_id)
    store.set_partial(download_id, split_partial(tmp_path))
    with closing(sqlite3.connect(tmp_path / "sdm.db")) as conn:
        conn.execute("UPDATE downloads SET segments = '[[0, 400, 0]]' WHERE id = ?", (download_id,))
        conn.commit()

    # A map that doesn't cover the file can't say which bytes are real: start over instead.
    assert store.get(download_id).partial() is None


def test_cancel_forgets_the_parts_map(store, tmp_path):
    download_id = store.add("https://example.com/a.zip", str(tmp_path)).id
    store.mark_downloading(download_id)
    store.set_partial(download_id, split_partial(tmp_path))
    store.mark_cancelled(download_id)
    assert store.get(download_id).segments is None
