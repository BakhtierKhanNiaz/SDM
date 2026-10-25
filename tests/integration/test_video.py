"""Video-page downloads (M12b) through the controller, with a fake yt-dlp (tests/fakes).

The page addresses are IP literals on this computer, allowed by the tests' loopback policy, so
no name is ever looked up and nothing leaves the machine.
"""

import json
import sqlite3
import sys
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest

from sdm.core.downloads import DownloadRecord, DownloadState
from sdm.engine.manager import Failed, Started
from sdm.engine.policy import NetworkPolicy
from sdm.ui.add_url_dialog import AddUrlDialog
from sdm.ui.preferences import Preferences
from sdm.ui.settings_dialog import SettingsDialog
from sdm.ui.video_runner import VideoRunner

FAKE_YTDLP = [sys.executable, str(Path(__file__).parent.parent / "fakes" / "fake_ytdlp.py")]
PAGE = "http://127.0.0.1:9/watch?v=abc123"


@pytest.fixture
def videos(make_controller, monkeypatch, tmp_path):
    controller = make_controller()
    controller.set_preferences(replace(controller.preferences, video_enabled=True))
    monkeypatch.setattr(controller, "_ytdlp_command", lambda: FAKE_YTDLP)
    folder = tmp_path / "Downloads"
    folder.mkdir()
    return controller, folder


def state_of(controller, download_id):
    return controller.store.get(download_id).state


def wait_for(qtbot, controller, download_id, state, timeout=20000):
    qtbot.waitUntil(lambda: state_of(controller, download_id) == state, timeout=timeout)


def test_a_video_page_downloads_into_one_file(qtbot, videos, monkeypatch, tmp_path):
    controller, folder = videos
    log = tmp_path / "args.json"
    monkeypatch.setenv("FAKE_YTDLP_LOG", str(log))
    record = controller.add(PAGE, folder, video="1080p")
    assert record.video == "1080p" and record.category == "Video"
    with qtbot.waitSignal(controller.download_finished, timeout=20000):
        pass
    done = controller.store.get(record.id)
    assert done.state == DownloadState.COMPLETED
    assert Path(done.path) == folder / "Test Video [abc123].mp4"
    assert Path(done.path).read_bytes() == b"v" * 1000 + b"a" * 300
    assert done.file_name == "Test Video [abc123].mp4"
    assert not (folder / ".sdm-video-1").exists()  # the work folder is cleaned up
    assert sorted(p.name for p in folder.iterdir()) == ["Test Video [abc123].mp4"]
    args = json.loads(log.read_text(encoding="utf-8"))
    assert args[0] == "--ignore-config" and args[-2:] == ["--", PAGE]
    assert args[args.index("-S") + 1] == "res:1080"


def test_audio_only_becomes_an_mp3(qtbot, videos):
    controller, folder = videos
    record = controller.add(PAGE, folder, video="mp3")
    assert record.category == "Music"
    wait_for(qtbot, controller, record.id, DownloadState.COMPLETED)
    assert (folder / "Test Video [abc123].mp3").read_bytes().startswith(b"audio:")


def test_a_second_copy_gets_a_numbered_name(qtbot, videos):
    controller, folder = videos
    (folder / "Test Video [abc123].mp4").write_bytes(b"earlier")
    record = controller.add(PAGE, folder, video="720p")
    wait_for(qtbot, controller, record.id, DownloadState.COMPLETED)
    assert Path(controller.store.get(record.id).path).name == "Test Video [abc123] (1).mp4"
    assert (folder / "Test Video [abc123].mp4").read_bytes() == b"earlier"


def test_an_unsupported_page_fails_with_a_plain_reason(qtbot, videos, monkeypatch):
    controller, folder = videos
    monkeypatch.setenv("FAKE_YTDLP_MODE", "fail")
    record = controller.add(PAGE, folder, video="720p")
    with qtbot.waitSignal(controller.download_failed, timeout=20000) as failed:
        pass
    assert failed.args == [record.id, "yt-dlp doesn't know how to download from this page."]
    assert state_of(controller, record.id) == DownloadState.FAILED


def test_pause_keeps_the_partial_files_and_resume_continues(qtbot, videos, monkeypatch):
    controller, folder = videos
    monkeypatch.setenv("FAKE_YTDLP_MODE", "slow")
    record = controller.add(PAGE, folder, video="1080p")
    work = folder / f".sdm-video-{record.id}"
    qtbot.waitUntil(lambda: controller.model.record(record.id).received_bytes == 500, timeout=20000)
    controller.pause(record.id)
    wait_for(qtbot, controller, record.id, DownloadState.PAUSED)
    assert (work / "Test Video [abc123].f137.mp4.part").exists()
    monkeypatch.setenv("FAKE_YTDLP_MODE", "ok")
    controller.resume(record.id)
    wait_for(qtbot, controller, record.id, DownloadState.COMPLETED)
    assert (folder / "Test Video [abc123].mp4").exists()
    assert not work.exists()


def test_cancel_stops_yt_dlp_and_deletes_its_files(qtbot, videos, monkeypatch):
    controller, folder = videos
    monkeypatch.setenv("FAKE_YTDLP_MODE", "slow")
    record = controller.add(PAGE, folder, video="720p")
    work = folder / f".sdm-video-{record.id}"
    qtbot.waitUntil(lambda: (work / "Test Video [abc123].f137.mp4.part").exists(), timeout=20000)
    controller.cancel(record.id)
    wait_for(qtbot, controller, record.id, DownloadState.CANCELLED)
    qtbot.waitUntil(lambda: not work.exists(), timeout=5000)
    assert list(folder.iterdir()) == []


def test_cancelling_a_paused_video_deletes_its_files(qtbot, videos, monkeypatch):
    controller, folder = videos
    monkeypatch.setenv("FAKE_YTDLP_MODE", "slow")
    record = controller.add(PAGE, folder, video="720p")
    work = folder / f".sdm-video-{record.id}"
    qtbot.waitUntil(lambda: work.exists(), timeout=20000)
    controller.pause(record.id)
    wait_for(qtbot, controller, record.id, DownloadState.PAUSED)
    assert work.exists()
    controller.cancel(record.id)
    assert state_of(controller, record.id) == DownloadState.CANCELLED
    assert not work.exists()


def test_closing_sdm_pauses_a_running_video(qtbot, videos, monkeypatch):
    controller, folder = videos
    monkeypatch.setenv("FAKE_YTDLP_MODE", "slow")
    record = controller.add(PAGE, folder, video="720p")
    qtbot.waitUntil(lambda: controller.model.record(record.id).received_bytes == 500, timeout=20000)
    controller.shutdown()
    assert state_of(controller, record.id) == DownloadState.PAUSED
    assert (folder / f".sdm-video-{record.id}").exists()  # resumed next time


def test_turned_off_or_missing_yt_dlp_is_explained(qtbot, videos, monkeypatch):
    controller, folder = videos
    controller.set_preferences(replace(controller.preferences, video_enabled=False))
    record = controller.add(PAGE, folder, video="720p")
    wait_for(qtbot, controller, record.id, DownloadState.FAILED)
    assert "turned off" in controller.store.get(record.id).error
    controller.set_preferences(replace(controller.preferences, video_enabled=True))
    monkeypatch.setattr(controller, "_ytdlp_command", lambda: None)
    other = controller.add(PAGE, folder, video="720p")
    wait_for(qtbot, controller, other.id, DownloadState.FAILED)
    assert "winget install yt-dlp.yt-dlp" in controller.store.get(other.id).error


def test_an_unknown_quality_is_refused(videos):
    controller, folder = videos
    from sdm.core.errors import SDMError

    with pytest.raises(SDMError):
        controller.add(PAGE, folder, video="8k")


def test_a_page_on_this_computer_is_blocked_before_yt_dlp_starts(qtbot, tmp_path):
    runner = VideoRunner()
    events = []
    runner.event.connect(events.append)
    record = DownloadRecord(1, "http://127.0.0.1/watch", str(tmp_path), False,
                            DownloadState.QUEUED, None, None, None, 0, None, None, "t", "t",
                            None, video="720p")  # fmt: skip
    runner.start(record, command=FAKE_YTDLP, ffmpeg=None, policy=NetworkPolicy())
    assert isinstance(events[0], Started) and isinstance(events[1], Failed)
    assert "this computer" in events[1].message
    assert not (tmp_path / ".sdm-video-1").exists()


def test_upgrading_the_history_to_version_7_keeps_entries(tmp_path):
    from sdm.storage import database
    from sdm.storage.database import DownloadStore

    path = tmp_path / "old.db"
    with closing(sqlite3.connect(path)) as conn:
        for script in database._MIGRATIONS[:6]:
            conn.executescript(script)
        conn.execute("PRAGMA user_version = 6")
        conn.execute(
            "INSERT INTO downloads (url, folder, state, created_at, updated_at)"
            " VALUES ('https://example.com/a.zip', 'D:', 'completed', 't', 't')"
        )
        conn.commit()
    store = DownloadStore(path)
    try:
        (record,) = store.list_all()
        assert record.video is None
        assert database.SCHEMA_VERSION == 7
    finally:
        store.close()


# ----- the window side -----


def test_turning_the_add_on_on_shows_the_notice(qtbot):
    dialog = SettingsDialog(Preferences(), tray_available=False)
    qtbot.addWidget(dialog)
    answers = [False, True]
    asked = []

    def confirm():
        asked.append(True)
        return answers.pop(0)

    dialog.confirm_video_terms = confirm
    dialog.video_check.setChecked(True)  # declined: stays off
    assert not dialog.video_check.isChecked()
    dialog.video_check.setChecked(True)  # accepted
    assert dialog.video_check.isChecked() and len(asked) == 2
    assert dialog.preferences().video_enabled is True


def test_the_notice_isnt_shown_again_once_accepted(qtbot):
    dialog = SettingsDialog(Preferences(video_enabled=True), tray_available=False)
    qtbot.addWidget(dialog)
    dialog.confirm_video_terms = lambda: pytest.fail("asked again")
    dialog.video_check.setChecked(False)
    dialog.video_check.setChecked(True)
    assert dialog.preferences().video_enabled is True


def test_add_url_offers_video_pages_only_when_turned_on(qtbot, tmp_path):
    off = AddUrlDialog(default_folder=tmp_path, previous_downloads=lambda url: [])
    qtbot.addWidget(off)
    off.kind_box.setCurrentIndex(2)
    assert off.video is None  # not offered, so never a video
    on = AddUrlDialog(default_folder=tmp_path, previous_downloads=lambda url: [],
                      video_enabled=True)  # fmt: skip
    qtbot.addWidget(on)
    assert on.video is None  # a file by default
    on.kind_box.setCurrentIndex(on.kind_box.findData("2160p"))
    assert on.video == "2160p"
    assert not on.sha256_edit.isEnabled()
