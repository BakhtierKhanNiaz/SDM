"""SDM's look (M11): Qt's "Fusion" style with a light or dark palette and a small stylesheet.

"system" follows Windows' own setting (Settings > Personalization > Colors) and switches when
it changes; "light" and "dark" force one. Colours meet WCAG AA contrast for text.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

MODES = ("system", "light", "dark")
MODE_LABELS = {"system": "Same as Windows", "light": "Light", "dark": "Dark"}

_LIGHT = {
    "window": "#f5f6f8", "base": "#ffffff", "alt": "#f7f8fa", "text": "#1f2328",
    "muted": "#5b636e", "accent": "#1f6feb", "accent_text": "#ffffff", "grid": "#e1e4e8",
    "header": "#eef0f3", "hover": "#e6eaf0", "button": "#ffffff",
}  # fmt: skip
_DARK = {
    "window": "#1c1f24", "base": "#22262c", "alt": "#272b32", "text": "#e6e8eb",
    "muted": "#9aa3ad", "accent": "#4c8dff", "accent_text": "#0d1117", "grid": "#343a42",
    "header": "#2a2f36", "hover": "#2f353d", "button": "#2a2f36",
}  # fmt: skip

_STYLE = """
QToolBar {{ spacing: 2px; padding: 4px 6px; border: none; background: {window}; }}
QToolBar QToolButton {{ padding: 5px 10px; border-radius: 6px; color: {text}; }}
QToolBar QToolButton:hover {{ background: {hover}; }}
QToolBar QToolButton:disabled {{ color: {muted}; }}
QTableView {{ border: none; gridline-color: {grid}; background: {base};
              alternate-background-color: {alt}; selection-background-color: {accent};
              selection-color: {accent_text}; }}
QHeaderView::section {{ padding: 6px 8px; border: none; border-bottom: 1px solid {grid};
                        border-right: 1px solid {grid}; background: {header}; color: {text};
                        font-weight: 600; }}
QStatusBar {{ border-top: 1px solid {grid}; color: {muted}; }}
QSplitter::handle {{ background: {grid}; }}
QFrame#details {{ background: {base}; border-top: 1px solid {grid}; }}
QLabel#detailsTitle {{ font-size: 11pt; font-weight: 600; }}
QLabel[muted="true"] {{ color: {muted}; }}
QProgressBar {{ border: 1px solid {grid}; border-radius: 4px; background: {alt};
                text-align: center; color: {text}; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 3px; }}
"""


def colors_for(dark: bool) -> dict[str, str]:
    return dict(_DARK if dark else _LIGHT)


def is_dark(mode: str, app: QApplication) -> bool:
    if mode == "dark":
        return True
    if mode == "light":
        return False
    return app.styleHints().colorScheme() == Qt.ColorScheme.Dark


def apply_theme(app: QApplication, mode: str) -> bool:
    """Apply the look for `mode` ("system", "light" or "dark"); returns True when dark."""
    mode = mode if mode in MODES else "system"
    dark = is_dark(mode, app)
    colors = colors_for(dark)
    if not app.property("sdm_fusion"):
        # Only once: setStyle() destroys the previous style object, and an open QWizard keeps
        # using it, which crashed SDM when the theme changed during the welcome assistant
        # (test_changing_the_theme_with_the_assistant_open). Later changes only swap colours.
        app.setStyle("Fusion")
        app.setProperty("sdm_fusion", True)
    app.setFont(QFont("Segoe UI", 10))
    palette = QPalette()
    for role, key in (
        (QPalette.ColorRole.Window, "window"),
        (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.Base, "base"),
        (QPalette.ColorRole.AlternateBase, "alt"),
        (QPalette.ColorRole.Text, "text"),
        (QPalette.ColorRole.Button, "button"),
        (QPalette.ColorRole.ButtonText, "text"),
        (QPalette.ColorRole.ToolTipBase, "base"),
        (QPalette.ColorRole.ToolTipText, "text"),
        (QPalette.ColorRole.PlaceholderText, "muted"),
        (QPalette.ColorRole.Highlight, "accent"),
        (QPalette.ColorRole.HighlightedText, "accent_text"),
        (QPalette.ColorRole.Link, "accent"),
    ):
        palette.setColor(role, QColor(colors[key]))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText):  # fmt: skip
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors["muted"]))
    app.setPalette(palette)
    app.setStyleSheet(_STYLE.format(**colors))
    app.setProperty("sdm_theme_mode", mode)
    app.setProperty("sdm_dark", dark)
    return dark


def follow_windows(app: QApplication) -> None:
    """Re-apply "system" when Windows switches between light and dark."""

    def changed(*_args: object) -> None:
        if app.property("sdm_theme_mode") == "system":
            apply_theme(app, "system")

    app.styleHints().colorSchemeChanged.connect(changed)
