"""File categories by type (M6), modelled on what IDM showed in OBS-001/002/005.

The list of extensions is our own. Categories are labels; they choose a subfolder only when
the owner turns that setting on (off by default).
"""

GENERAL = "General"
CATEGORIES = (GENERAL, "Compressed", "Documents", "Music", "Video", "Programs")

_EXTENSIONS = {
    "Compressed": {
        "zip", "rar", "7z", "gz", "tgz", "bz2", "xz", "zst", "tar", "cab", "iso", "img",
    },
    "Documents": {
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp", "rtf", "txt",
        "csv", "epub", "md",
    },
    "Music": {"mp3", "flac", "wav", "ogg", "opus", "m4a", "aac", "wma"},
    "Video": {"mp4", "mkv", "avi", "mov", "webm", "wmv", "m4v", "mpg", "mpeg", "flv"},
    "Programs": {"exe", "msi", "msix", "appx", "bat", "cmd", "ps1", "apk", "dmg", "deb", "rpm"},
}  # fmt: skip
_BY_EXTENSION = {ext: name for name, exts in _EXTENSIONS.items() for ext in exts}


def category_for(file_name: str | None) -> str:
    """'setup.exe' -> 'Programs', 'archive.tar.gz' -> 'Compressed', 'stream' -> 'General'."""
    if not file_name or "." not in file_name.strip(". "):
        return GENERAL
    extension = file_name.rsplit(".", 1)[1].strip().lower()
    return _BY_EXTENSION.get(extension, GENERAL)
