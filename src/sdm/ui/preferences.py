"""SDM's own settings (M9), kept in the history's settings table like the queue's (M6).

Each value is checked when read: anything missing or damaged falls back to its default, so a
bad row can never stop SDM from starting.
"""

from dataclasses import dataclass, fields

from sdm.storage.database import DownloadStore

MAX_SPEED_LIMIT_KIB = 1_000_000  # KB/s; about 1 GB/s, i.e. "no practical limit"
MAX_FOLDER_LENGTH = 1000


@dataclass(frozen=True)
class Preferences:
    speed_limit_kib: int = 0  # all downloads together, in KB/s (1 KB = 1024 bytes); 0 = none
    connections: int = 8  # per download, 1-8 (1 never splits)
    default_folder: str = ""  # "" = the user's Downloads folder
    remember_last_folder: bool = True  # Add URL offers the folder used last time
    last_folder: str = ""
    keep_in_tray: bool = False  # closing the window hides it; SDM keeps running
    notify: bool = True  # a Windows notification when a download finishes or fails

    @property
    def speed_limit_bytes(self) -> int | None:
        return self.speed_limit_kib * 1024 if self.speed_limit_kib > 0 else None

    def checked(self) -> "Preferences":
        """The same values, with anything out of range replaced by its default."""
        default = Preferences()
        values = {}
        for field in fields(self):
            value = getattr(self, field.name)
            if type(value) is not type(getattr(default, field.name)):
                value = getattr(default, field.name)
            values[field.name] = value
        if not 0 <= values["speed_limit_kib"] <= MAX_SPEED_LIMIT_KIB:
            values["speed_limit_kib"] = default.speed_limit_kib
        if not 1 <= values["connections"] <= 8:
            values["connections"] = default.connections
        for name in ("default_folder", "last_folder"):
            if len(values[name]) > MAX_FOLDER_LENGTH or "\x00" in values[name]:
                values[name] = ""
        return Preferences(**values)


_PREFIX = "prefs."


def load_preferences(store: DownloadStore) -> Preferences:
    default = Preferences()
    values = {}
    for field in fields(Preferences):
        raw = store.get_setting(_PREFIX + field.name)
        if raw is None:
            continue
        kind = type(getattr(default, field.name))
        try:
            if kind is bool:
                if raw not in ("0", "1"):
                    continue
                values[field.name] = raw == "1"
            elif kind is int:
                values[field.name] = int(raw)
            else:
                values[field.name] = raw
        except ValueError:
            continue
    return Preferences(**values).checked()


def save_preferences(store: DownloadStore, preferences: Preferences) -> None:
    for field in fields(Preferences):
        value = getattr(preferences.checked(), field.name)
        text = ("1" if value else "0") if isinstance(value, bool) else str(value)
        store.set_setting(_PREFIX + field.name, text)
