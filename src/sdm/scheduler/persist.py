"""Saving and loading the queue settings in the history database's settings table (M6)."""

from sdm.scheduler.queue import DEFAULT_LIMIT, QueueSettings, Schedule
from sdm.storage.database import DownloadStore

_LIMIT, _SCHEDULE, _SUBFOLDERS = "queue.limit", "queue.schedule", "categories.subfolders"


def load_queue_settings(store: DownloadStore) -> QueueSettings:
    try:
        limit = int(store.get_setting(_LIMIT) or DEFAULT_LIMIT)
    except ValueError:
        limit = DEFAULT_LIMIT
    return QueueSettings(
        limit=limit,
        schedule=Schedule.from_json(store.get_setting(_SCHEDULE)),
        category_subfolders=store.get_setting(_SUBFOLDERS) == "1",
    )


def save_queue_settings(store: DownloadStore, settings: QueueSettings) -> None:
    store.set_setting(_LIMIT, str(settings.limit))
    store.set_setting(_SCHEDULE, settings.schedule.to_json())
    store.set_setting(_SUBFOLDERS, "1" if settings.category_subfolders else "0")
