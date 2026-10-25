"""SDM's own icons (M13): the logo for the window, the tray and every dialog.

The PNGs are made from assets/sdm.svg by scripts/make_icons.py.
"""

from pathlib import Path

from PySide6.QtGui import QIcon

ASSETS = Path(__file__).resolve().parent / "assets"
LOGO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def app_icon() -> QIcon:
    """The SDM logo in every size Windows asks for (title bar, taskbar, Alt+Tab, tray)."""
    icon = QIcon()
    for size in LOGO_SIZES:
        icon.addFile(str(ASSETS / f"sdm-{size}.png"))
    return icon
