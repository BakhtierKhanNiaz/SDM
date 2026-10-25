"""The welcome assistant (M11): download folder, look, and browsers, on first start.

It opens by itself the first time SDM starts, and later from Help > Setup assistant. Nothing
here needs PowerShell: browsers are detected, and SDM registers its helper for the ticked ones
(the extension IDs are fixed, so nothing is typed in).
"""

import html
import subprocess
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
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

from sdm.bridge.browsers import (
    BROWSERS,
    EXTENSIONS_PAGE,
    Browser,
    extension_folder,
    open_extensions_page,
)
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
            "SDM registers itself for the ticked browsers. Then add SDM's extension to each "
            "one: press its Add button and follow the three steps."
        )
        browsers_layout = QVBoxLayout(browsers_page)
        self.browser_checks: dict[str, QCheckBox] = {}
        self.add_buttons: dict[str, QPushButton] = {}
        for browser in BROWSERS:
            present = browser.key in installed
            check = QCheckBox(browser.name + ("" if present else "  (not installed)"))
            check.setChecked(present)
            check.setEnabled(present)
            if browser.key in EXTENSIONS_PAGE:  # M13: the extension comes with SDM
                add = QPushButton(f"Add to {browser.name.split()[-1]}")
                add.clicked.connect(lambda _=False, b=browser: self.add_extension(b))
            else:
                add = QPushButton("Get the add-on")
                add.clicked.connect(lambda _=False, b=browser: self.open_extension_page(b))
            add.setEnabled(present)
            line = QHBoxLayout()
            line.addWidget(check)
            line.addStretch()
            line.addWidget(add)
            browsers_layout.addLayout(line)
            self.browser_checks[browser.key] = check
            self.add_buttons[browser.key] = add
        # The steps for the browser whose Add button was pressed last (M13).
        self.guide = _text(
            "<br>Firefox only installs add-ons signed by Mozilla: its button opens SDM's page. "
            "Afterwards, start downloads as usual, or right-click a link and choose "
            "<b>Download with SDM</b>."
        )
        browsers_layout.addWidget(self.guide)
        browsers_layout.addStretch()

        for page in (welcome, folder_page, browsers_page):
            self.addPage(page)
        self.opened: list[str] = []  # extension pages opened (tests read it)
        self.launch = subprocess.Popen  # starts a browser (tests replace it)

    def _browse(self) -> None:
        start = self.folder_edit.text()
        chosen = QFileDialog.getExistingDirectory(self, "Save downloads to", start)
        if chosen:
            self.folder_edit.setText(str(Path(chosen)))

    def open_extension_page(self, browser: Browser) -> None:
        url = extension_page(browser.key)
        self.opened.append(url)
        QDesktopServices.openUrl(QUrl(url))

    def add_extension(self, browser: Browser) -> bool:
        """Guide the user through "Load unpacked" (M13; a free alternative to a store): copy
        the folder of the extension that came with SDM and open the browser's extensions
        page. Browsers don't let programs add extensions by themselves."""
        folder = extension_folder()
        QGuiApplication.clipboard().setText(str(folder))
        opened = open_extensions_page(browser, launch=self.launch)
        page = EXTENSIONS_PAGE[browser.key]
        where = "In the window that opened" if opened else f"Open <b>{page}</b> in {browser.name}"
        self.guide.setText(
            f"<br><b>Add SDM to {html.escape(browser.name)}:</b> {where},<br>"
            "1. turn on <b>Developer mode</b> (top right),<br>"
            "2. click <b>Load unpacked</b>,<br>"
            "3. press <b>Ctrl+V</b> in the folder box (SDM copied the folder for you) and "
            "choose <b>Select Folder</b>.<br>"
            f"<small>Folder: {html.escape(str(folder))}</small>"
        )
        return opened

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
