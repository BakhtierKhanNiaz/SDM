"""SDM's own line icons (M13) for the toolbar, the sidebar and the file types in the list.

Each is a 24x24 drawing of a few strokes, coloured when drawn, so the same icon suits the light
and the dark look. Drawn for SDM (no icon set copied).
"""

from functools import cache

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS = {
    # toolbar
    "add": "M12 5v14 M5 12h14",
    "pause": "M8 5v14 M16 5v14",
    "resume": "M7 4.5l12 7.5-12 7.5z",
    "resume_all": "M4 5l8 7-8 7z M13 5l8 7-8 7z",
    "cancel": "M12 3a9 9 0 1 0 0.01 0z M8.5 8.5l7 7 M15.5 8.5l-7 7",
    "remove": "M4 7h16 M9 7V4h6v3 M6 7l1 13h10l1-13 M10 11v6 M14 11v6",
    "start_now": "M13 2L5 14h6l-1 8 8-12h-6z",
    "scheduler": "M12 3a9 9 0 1 0 0.01 0z M12 7v5l3 3",
    "convert": "M4 9a8 8 0 0 1 14-3l2 2 M20 4v4h-4 M20 15a8 8 0 0 1-14 3l-2-2 M4 20v-4h4",
    "settings": "M12 9a3 3 0 1 0 0.01 0z M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 "
    "M17 17l2 2 M5 19l2-2 M17 7l2-2",
    # sidebar views
    "all": "M4 6h16 M4 12h16 M4 18h16",
    "downloading": "M12 4v12 M7 11l5 5 5-5 M5 20h14",
    "finished": "M12 3a9 9 0 1 0 0.01 0z M8 12l3 3 5-6",
    "unfinished": "M12 3a9 9 0 1 0 0.01 0z M12 7v6 M12 16.5v0.5",
    # file types (categories)
    "General": "M6 3h8l4 4v14H6z M14 3v4h4",
    "Compressed": "M6 3h12v18H6z M11 3v2h2V3 M11 7h2 M11 9h2 M11 11h2 M10 13h4v4h-4z",
    "Documents": "M6 3h8l4 4v14H6z M14 3v4h4 M9 12h6 M9 15h6 M9 18h4",
    "Music": "M9 18V5l11-2v13 M9 18a3 3 0 1 1-0.01 0z M20 16a3 3 0 1 1-0.01 0z",
    "Video": "M3 6h13v12H3z M16 10l5-3v10l-5-3",
    "Programs": "M3 5h18v14H3z M3 9h18 M7 13l2 2-2 2 M11 17h4",
}
NAMES = tuple(_PATHS)

# The file types' own colours, readable on both looks.
CATEGORY_COLOURS = {
    "General": "#6b7280", "Compressed": "#d97706", "Documents": "#2563eb",
    "Music": "#db2777", "Video": "#7c3aed", "Programs": "#0f766e",
}  # fmt: skip


def _svg(name: str, colour: str) -> bytes:
    filled = name in ("resume", "resume_all", "start_now")
    fill = colour if filled else "none"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        f'<path d="{_PATHS[name]}" fill="{fill}" stroke="{colour}" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>'
    ).encode()


@cache
def _pixmap(name: str, colour: str, size: int) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(_svg(name, colour)))
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return QPixmap.fromImage(image)


def glyph(name: str, colour: str, *, disabled: str | None = None) -> QIcon:
    """The icon `name` in `colour` (and `disabled` for a greyed-out button)."""
    icon = QIcon()
    for size in (16, 20, 24, 32, 48):
        icon.addPixmap(_pixmap(name, colour, size), QIcon.Mode.Normal)
        if disabled:
            icon.addPixmap(_pixmap(name, disabled, size), QIcon.Mode.Disabled)
    return icon


def category_glyph(category: str) -> QIcon:
    name = category if category in CATEGORY_COLOURS else "General"
    return glyph(name, CATEGORY_COLOURS[name])


ICON_SIZE = QSize(22, 22)
