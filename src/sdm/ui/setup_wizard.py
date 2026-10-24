"""The welcome assistant (M11): download folder, look, and browsers, on first start.

It opens by itself the first time SDM starts, and later from Help > Setup assistant. Nothing
here needs PowerShell: browsers are detected, and SDM registers its helper for the ticked ones
(the extension IDs are fixed, so nothing is typed in).
"""

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from sdm.bridge.browsers import BROWSERS, Browser
from sdm.core.links import extension_page
from sdm.ui.preferences import Preferences
from sdm.ui.theme import MODE_LABELS, MODES


def _text(html: str) -> QLabel:
    label = QLabel(html)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)  # only our own fixed text, never user data
    label.setOpenExternalLinks(True)
    return label


class SetupWizard(QWizard):
    def __init__(
        self,
        preferences: Preferences,
        *,
        installed: set[str],
        default_folder: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome to SDM")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setMinimumSize(620, 460)
        self._preferences = preferences
        self.installed = installed

        welcome = QWizardPage()
        welcome.setTitle("Welcome to SDM")
        welcome.setSubTitle("Three quick choices and you're ready.")
        layout = QVBoxLayout(welcome)
        layout.addWidget(_text(
            "SDM downloads big files over several connections at once, pauses and resumes "
            "them, and can take downloads straight from your browser.<br><br>"
            "Next: where downloads go, how SDM looks, and which browsers to connect. You can "
            "change everything later in <b>Tools &gt; Settings</b> and "
            "<b>Help &gt; Setup assistant</b>."
        ))  # fmt: skip

        folder_page = QWizardPage()
        folder_page.setTitle("Downloads and appearance")
        self.folder_edit = QLineEdit(preferences.default_folder or str(default_folder))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.folder_edit)
        row.addWidget(browse)
        self.remember_check = QCheckBox("Offer the folder I used last time")
        self.remember_check.setChecked(preferences.remember_last_folder)
        self.theme_box = QComboBox()
        for mode in MODES:
            self.theme_box.addItem(MODE_LABELS[mode], mode)
        self.theme_box.setCurrentIndex(max(0, self.theme_box.findData(preferences.theme)))
        form = QFormLayout(folder_page)
        form.addRow("Save downloads to:", row)
        form.addRow(self.remember_check)
        form.addRow("Appearance:", self.theme_box)

        browsers_page = QWizardPage()
        browsers_page.setTitle("Connect your browsers")
        browsers_page.setSubTitle(
            "SDM registers itself for the ticked browsers, so its extension can hand downloads "
            "to SDM. Then install the extension in each browser."
        )
        browsers_layout = QVBoxLayout(browsers_page)
        self.browser_checks: dict[str, QCheckBox] = {}
        for browser in BROWSERS:
            present = browser.key in installed
            check = QCheckBox(browser.name + ("" if present else "  (not installed)"))
            check.setChecked(present)
            check.setEnabled(present)
            get = QPushButton("Get the extension")
            get.setEnabled(present)
            get.clicked.connect(lambda _=False, b=browser: self.open_extension_page(b))
            line = QHBoxLayout()
            line.addWidget(check)
            line.addStretch()
            line.addWidget(get)
            browsers_layout.addLayout(line)
            self.browser_checks[browser.key] = check
        browsers_layout.addWidget(_text(
            "<br>Chrome and Brave: unzip <i>sdm-chromium</i> from the release page, open "
            "<i>chrome://extensions</i>, turn on Developer mode and choose Load unpacked. "
            "Edge: from Microsoft Edge Add-ons, or the same way as Chrome. Firefox: from "
            "Firefox Add-ons (Firefox only installs add-ons signed by Mozilla). Then start "
            "downloads as usual, or right-click a link and choose <b>Download with SDM</b>."
        ))  # fmt: skip
        browsers_layout.addStretch()

        for page in (welcome, folder_page, browsers_page):
            self.addPage(page)
        self.opened: list[str] = []  # extension pages opened (tests read it)

    def _browse(self) -> None:
        start = self.folder_edit.text()
        chosen = QFileDialog.getExistingDirectory(self, "Save downloads to", start)
        if chosen:
            self.folder_edit.setText(str(Path(chosen)))

    def open_extension_page(self, browser: Browser) -> None:
        url = extension_page(browser.key)
        self.opened.append(url)
        QDesktopServices.openUrl(QUrl(url))

    def chosen_browsers(self) -> list[Browser]:
        return [b for b in BROWSERS if self.browser_checks[b.key].isChecked()]

    def preferences(self) -> Preferences:
        folder = self.folder_edit.text().strip()
        return replace(
            self._preferences,
            default_folder=folder if folder and Path(folder).is_dir() else "",
            remember_last_folder=self.remember_check.isChecked(),
            theme=self.theme_box.currentData(),
            setup_done=True,
        )
