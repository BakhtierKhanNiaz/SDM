"""Where SDM keeps its per-user files."""

import os
from pathlib import Path


def app_data_dir() -> Path:
    """%LOCALAPPDATA%\\SDM: per-user, and outside Controlled Folder Access's folders."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "SDM"
