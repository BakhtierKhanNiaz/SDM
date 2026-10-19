"""Speed limit, connections per download, checksums and notifications, through the window code
and a local server (M9)."""

import hashlib
import os
import time

import pytest

from sdm.core.checksums import MISMATCH, MISSING, VERIFIED, InvalidChecksumError
from sdm.core.downloads import DownloadState
from sdm.ui.controller import finished_file
from sdm.ui.preferences import Preferences

MIB = 1024 * 1024


def wait_for_state(qtbot, controller, download_id, state, timeout=20_000):
    qtbot.waitUntil(lambda: controller.store.get(download_id).state == state, timeout=timeout)


def elapsed_download(qtbot, controller, url, folder, **add):
    started = time.monotonic()
    record = controller.add(url, folder, **add)
    wait_for_state(qtbot, controller, record.id, DownloadState.COMPLETED)
    return record.id, time.monotonic() - started


def test_the_speed_limit_holds_for_one_connection(qtbot, make_controller, mock_server, tmp_path):
    data = os.urandom(MIB)
    mock_server.add("/a.bin", mock_server.file(data))
    controller = make_controller()
    controller.set_preferences(Preferences(speed_limit_kib=512))
    download_id, seconds = elapsed_download(qtbot, controller, mock_server.url("/a.bin"), tmp_path)
    assert 1.6 <= seconds <= 4.5  # 1 MiB at 512 KiB/s is about 2 s; unlimited, well under 1 s
    assert (tmp_path / "a.bin").read_bytes() == data


def test_split_connections_share_the_limit(qtbot, make_controller, mock_server, tmp_path):
    data = os.urandom(3 * MIB)
    mock_server.add("/big.bin", mock_server.ranged(data, etag='"v1"'))
    controller = make_controller()
    controller.set_preferences(Preferences(speed_limit_kib=1024))
    _, seconds = elapsed_download(qtbot, controller, mock_server.url("/big.bin"), tmp_path)
    assert len(mock_server.requests) > 1  # it did split
    assert 2.4 <= seconds <= 6.0  # 3 MiB at 1 MiB/s, whatever the number of connections
    assert (tmp_path / "big.bin").read_bytes() == data


def test_lifting_the_limit_speeds_up_a_running_download(
    qtbot, make_controller, mock_server, tmp_path
):
    data = os.urandom(2 * MIB)
    mock_server.add("/a.bin", mock_server.file(data))
    controller = make_controller()
    controller.set_preferences(Preferences(speed_limit_kib=64))  # would take about 32 s
    record = controller.add(mock_server.url("/a.bin"), tmp_path)
    qtbot.waitUntil(lambda: controller.model.record(record.id).received_bytes > 0, timeout=10_000)
    started = time.monotonic()
    controller.set_preferences(Preferences(speed_limit_kib=0))
    wait_for_state(qtbot, controller, record.id, DownloadState.COMPLETED, timeout=10_000)
    assert time.monotonic() - started < 5


def test_one_connection_per_download_never_splits(qtbot, make_controller, mock_server, tmp_path):
    data = os.urandom(3 * MIB)
    mock_server.add("/big.bin", mock_server.ranged(data, etag='"v1"'))
    controller = make_controller()
    controller.set_preferences(Preferences(connections=1))
    elapsed_download(qtbot, controller, mock_server.url("/big.bin"), tmp_path)
    assert len(mock_server.requests) == 1
    assert "Range" not in mock_server.requests[0]


# ----- checksums -----

DATA = os.urandom(200_000)
GOOD = hashlib.sha256(DATA).hexdigest()


@pytest.fixture
def served(mock_server):
    mock_server.add("/f.bin", mock_server.file(DATA))
    return mock_server.url("/f.bin")


def test_a_matching_checksum_is_verified(qtbot, make_controller, served, tmp_path):
    controller = make_controller()
    results = []
    controller.checksum_checked.connect(lambda i, state: results.append(state))
    download_id, _ = elapsed_download(qtbot, controller, served, tmp_path,
                                      expected_sha256=GOOD.upper())  # fmt: skip
    qtbot.waitUntil(lambda: results == [VERIFIED], timeout=5_000)
    record = controller.store.get(download_id)
    assert (record.expected_sha256, record.checksum_state) == (GOOD, VERIFIED)
    assert controller.model.data(controller.model.index(0, 6)) == "Completed · verified"


def test_a_mismatch_keeps_the_file_and_says_so(qtbot, make_controller, served, tmp_path):
    controller = make_controller()
    results = []
    controller.checksum_checked.connect(lambda i, state: results.append(state))
    download_id, _ = elapsed_download(qtbot, controller, served, tmp_path,
                                      expected_sha256="0" * 64)  # fmt: skip
    qtbot.waitUntil(lambda: results == [MISMATCH], timeout=5_000)
    record = controller.store.get(download_id)
    assert record.state == DownloadState.COMPLETED
    assert (tmp_path / "f.bin").read_bytes() == DATA  # never deleted
    assert "checksum doesn't match" in controller.model.data(controller.model.index(0, 6))


def test_checking_a_finished_file_later(qtbot, make_controller, served, tmp_path):
    controller = make_controller()
    results = []
    controller.checksum_checked.connect(lambda i, state: results.append(state))
    download_id, _ = elapsed_download(qtbot, controller, served, tmp_path)
    assert controller.store.get(download_id).checksum_state is None
    controller.verify(download_id, GOOD)
    qtbot.waitUntil(lambda: results == [VERIFIED], timeout=5_000)


def test_a_missing_file_cant_be_checked(qtbot, make_controller, served, tmp_path):
    controller = make_controller()
    results = []
    controller.checksum_checked.connect(lambda i, state: results.append(state))
    download_id, _ = elapsed_download(qtbot, controller, served, tmp_path)
    (tmp_path / "f.bin").unlink()
    controller.verify(download_id, GOOD)
    assert results == [MISSING]


def test_a_malformed_checksum_is_refused_before_adding(make_controller, served, tmp_path):
    controller = make_controller()
    with pytest.raises(InvalidChecksumError):
        controller.add(served, tmp_path, expected_sha256="not a checksum")
    assert controller.model.records() == []


def test_a_finished_path_outside_its_folder_is_never_used(make_controller, tmp_path):
    from dataclasses import replace

    controller = make_controller()
    record = controller.store.add("https://example.com/a", str(tmp_path / "folder"))
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("not SDM's", encoding="utf-8")
    done = replace(record, state=DownloadState.COMPLETED, path=str(outside))
    assert finished_file(done) is None  # a tampered history can't point SDM elsewhere


# ----- notifications -----


def test_finishing_and_failing_are_announced_once(qtbot, make_controller, mock_server, tmp_path):
    mock_server.add("/ok.bin", mock_server.file(DATA))
    controller = make_controller()
    finished, failed = [], []
    controller.download_finished.connect(finished.append)
    controller.download_failed.connect(lambda i, message: failed.append((i, message)))
    ok_id, _ = elapsed_download(qtbot, controller, mock_server.url("/ok.bin"), tmp_path)
    missing = controller.add(mock_server.url("/missing.bin"), tmp_path)  # 404: no retry
    wait_for_state(qtbot, controller, missing.id, DownloadState.FAILED)
    assert finished == [ok_id]
    assert [i for i, _ in failed] == [missing.id]
    assert "not found" in failed[0][1]


def test_a_temporary_failure_with_retries_left_isnt_announced(
    qtbot, make_controller, mock_server, tmp_path
):
    mock_server.add("/busy.bin", mock_server.status(503))
    controller = make_controller()
    failed = []
    controller.download_failed.connect(lambda i, message: failed.append(i))
    record = controller.add(mock_server.url("/busy.bin"), tmp_path)
    qtbot.waitUntil(lambda: controller.store.get(record.id).retry_at is not None, timeout=15_000)
    assert failed == []  # it will retry by itself in about a minute


def test_upgrading_to_version_6_keeps_entries(tmp_path):
    import sqlite3
    from contextlib import closing

    from sdm.storage import database
    from sdm.storage.database import DownloadStore

    path = tmp_path / "old.db"
    with closing(sqlite3.connect(path)) as conn:
        for script in database._MIGRATIONS[:5]:  # a version-5 history, as M8 left it
            conn.executescript(script)
        conn.execute("PRAGMA user_version = 5")
        conn.execute(
            "INSERT INTO downloads (url, folder, state, file_name, created_at, updated_at,"
            " referrer) VALUES ('https://example.com/a.zip', 'D:', 'completed', 'a.zip', 't',"
            " 't', 'https://example.com/')"
        )
        conn.commit()
    store = DownloadStore(path)
    try:
        (record,) = store.list_all()
        assert record.referrer == "https://example.com/"
        assert (record.expected_sha256, record.checksum_state) == (None, None)
        assert database.SCHEMA_VERSION == 6
    finally:
        store.close()
