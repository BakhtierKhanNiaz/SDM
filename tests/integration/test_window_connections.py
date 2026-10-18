"""The window shows how many connections a split download uses (M5b)."""

import os
from dataclasses import replace
from pathlib import Path

from sdm.core.downloads import DownloadRecord, DownloadState
from sdm.engine.models import DownloadSettings
from sdm.storage.database import DownloadStore
from sdm.ui.controller import DownloadController
from sdm.ui.download_model import STATUS, cell_text

DATA = os.urandom(800_000)
SPLIT = DownloadSettings(
    connect_timeout=5.0,
    read_timeout=10.0,
    backoff_base=0.0,
    max_connections=4,
    min_split_size=200_000,
    min_part_size=100_000,
)


def test_status_text_names_the_connections():
    record = DownloadRecord(
        1, "https://example.com/a", "D:\\", False, DownloadState.DOWNLOADING, "a.zip", None,
        800_000, 1000, None, None, "t", "t", None,
    )  # fmt: skip
    assert cell_text(record, STATUS, connections=4) == "Downloading · 4 connections"
    assert cell_text(record, STATUS, connections=1) == "Downloading"
    finished = replace(record, state=DownloadState.COMPLETED)
    assert cell_text(finished, STATUS, connections=4) == "Completed"


def test_a_split_download_shows_its_connections(
    qtbot, qapp, tmp_path, loopback_policy, mock_server
):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    mock_server.add("/data.bin", mock_server.ranged(DATA, etag='"v1"', rate=200_000))
    store = DownloadStore(tmp_path / "sdm.db")
    controller = DownloadController(store, policy_for=lambda r: loopback_policy, settings=SPLIT)
    controller.start()
    try:
        record = controller.add(mock_server.url("/data.bin"), downloads)
        model = controller.model
        qtbot.waitUntil(
            lambda: "4 connections" in model.data(model.index(0, STATUS)), timeout=10_000
        )
        qtbot.waitUntil(
            lambda: controller.store.get(record.id).state == DownloadState.COMPLETED,
            timeout=15_000,
        )
        assert model.data(model.index(0, STATUS)) == "Completed"
        assert Path(controller.store.get(record.id).path).read_bytes() == DATA
    finally:
        controller.shutdown()
        store.close()
