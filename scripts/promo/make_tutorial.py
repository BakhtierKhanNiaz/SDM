"""SDM's how-to video: download, install, connect the browser, use it (about 67 s, 16:9).

    uv run python scripts/promo/make_tutorial.py   # dist\\promo\\sdm-<version>-tutorial-wide.mp4

Built like make_promo.py (it reuses its drawing and SDM's real windows). The GitHub page and
Windows' SmartScreen warning are drawn as simple illustrations, labelled as such by their
plain look; every SDM window is the real one. Add the voice and music with
make_promo_audio.py ... tutorial.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_promo as mp  # noqa: E402
from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QPen  # noqa: E402

from sdm import __version__  # noqa: E402
from sdm.bridge import browsers  # noqa: E402
from sdm.media.ffmpeg import find_ffmpeg  # noqa: E402
from sdm.ui import setup_wizard  # noqa: E402
from sdm.ui.preferences import Preferences  # noqa: E402

phase, text, picture, cursor = mp.phase, mp.text, mp.picture, mp.cursor
INSTALLED_EXTENSION = Path(r"C:\Users\you\AppData\Local\Programs\SDM\extension")


def wizard_image(app) -> object:
    """The real welcome assistant, after "Add to Chrome" (no browser is really started)."""
    browsers.program_path = lambda browser: Path("chrome.exe")
    setup_wizard.extension_folder = lambda: INSTALLED_EXTENSION  # as in the installed SDM
    wizard = setup_wizard.SetupWizard(Preferences(), installed={"chrome", "edge"},
                                      default_folder=mp.FOLDER)  # fmt: skip
    wizard.launch = lambda args: None
    wizard.setStartId(wizard.pageIds()[-1])
    wizard.show()
    wizard.add_buttons["chrome"].click()
    app.processEvents()
    image = wizard.grab().toImage()
    wizard.close()
    return image


def window_frame(p, rect: QRectF, title: str, s: float) -> QRectF:
    """A plain browser window; returns the page area."""
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#202124"))
    p.drawRoundedRect(rect, 14 * s, 14 * s)
    bar = QRectF(rect.x() + 16 * s, rect.y() + 14 * s, rect.width() - 32 * s, 34 * s)
    p.setBrush(QColor("#303134"))
    p.drawRoundedRect(bar, 17 * s, 17 * s)
    p.restore()
    text(p, bar.adjusted(18 * s, 7 * s, 0, 0), 15 * s, "#bdc1c6", title,
         align=Qt.AlignmentFlag.AlignLeft)  # fmt: skip
    page = QRectF(rect.x(), rect.y() + 62 * s, rect.width(), rect.height() - 62 * s)
    p.fillRect(page, QColor("#0d1117"))
    return page


def github_page(p, w, h, t, st):
    s = mp.scale_of(w, h)
    rect = QRectF(w * 0.17, h * 0.3, w * 0.66, h * 0.62)
    p.save()
    p.setOpacity(phase(t, 0, 0.5))
    page = window_frame(p, rect, "github.com/Conditions-tech/SDM/releases/latest", s)
    text(p, QRectF(page.x() + 40 * s, page.y() + 30 * s, 800 * s, 50 * s), 34 * s, "#e6edf3",
         f"SDM {__version__}", weight=QFont.Weight.Bold,
         align=Qt.AlignmentFlag.AlignLeft)  # fmt: skip
    text(p, QRectF(page.x() + 40 * s, page.y() + 90 * s, 600 * s, 40 * s), 22 * s, "#e6edf3",
         "Assets", weight=QFont.Weight.DemiBold, align=Qt.AlignmentFlag.AlignLeft)  # fmt: skip
    files = [f"SDM-Setup-{__version__}.exe", f"SDM-{__version__}-portable.zip",
             f"sdm-chromium-{__version__}.zip", "SHA256SUMS.txt"]  # fmt: skip
    rows = []
    for i, name in enumerate(files):
        row = QRectF(
            page.x() + 40 * s, page.y() + (140 + i * 52) * s, page.width() - 80 * s, 46 * s
        )
        p.setPen(QPen(QColor("#30363d"), 1))
        p.setBrush(QColor("#161b22") if i else QColor(56, 139, 253, 40))
        p.drawRoundedRect(row, 6 * s, 6 * s)
        text(p, row.adjusted(16 * s, 11 * s, 0, 0), 19 * s, "#58a6ff", name,
             align=Qt.AlignmentFlag.AlignLeft)  # fmt: skip
        rows.append(row)
    p.restore()
    target = QPointF(rows[0].x() + 140 * s, rows[0].center().y())
    start = QPointF(rect.right() - 100 * s, rect.bottom() - 60 * s)
    at = start + (target - start) * phase(t, 2.5, 1.6)
    if t >= 4.3:
        ring = phase(t, 4.3, 0.5)
        p.save()
        p.setOpacity(1 - ring)
        p.setPen(QPen(mp.ACCENT, 3 * s))
        p.drawEllipse(target, 10 * s + 36 * s * ring, 10 * s + 36 * s * ring)
        p.restore()
    cursor(p, at, 1.4 * s, 4.3 <= t < 4.55)


def smartscreen(p, w, h, t, st):
    s = mp.scale_of(w, h)
    box = QRectF(w * 0.25, h * 0.3, w * 0.5, h * 0.56)
    p.save()
    p.setOpacity(phase(t, 0, 0.5))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#1f4e91"))
    p.drawRect(box)
    text(p, QRectF(box.x() + 40 * s, box.y() + 40 * s, box.width() - 80 * s, 60 * s), 38 * s,
         "#ffffff", "Windows protected your PC", align=Qt.AlignmentFlag.AlignLeft)  # fmt: skip
    text(p, QRectF(box.x() + 40 * s, box.y() + 110 * s, box.width() - 80 * s, 90 * s), 20 * s,
         "#dbe6f6", "Microsoft Defender SmartScreen prevented an unrecognised app from starting.",
         align=Qt.AlignmentFlag.AlignLeft)  # fmt: skip
    more = QRectF(box.x() + 40 * s, box.y() + 190 * s, 140 * s, 30 * s)
    text(p, more, 20 * s, "#ffffff", "More info", weight=QFont.Weight.DemiBold,
         align=Qt.AlignmentFlag.AlignLeft)  # fmt: skip
    expanded = t >= 3.4
    run = QRectF(box.right() - 360 * s, box.bottom() - 80 * s, 160 * s, 48 * s)
    if expanded:
        text(p, QRectF(box.x() + 40 * s, box.y() + 240 * s, box.width() - 80 * s, 70 * s),
             19 * s, "#dbe6f6", f"App: SDM-Setup-{__version__}.exe\nPublisher: Unknown publisher",
             align=Qt.AlignmentFlag.AlignLeft)  # fmt: skip
        p.setBrush(QColor("#2b5797"))
        p.setPen(QPen(QColor("#ffffff"), 1.5))
        p.drawRect(run)
        text(p, run.adjusted(0, 12 * s, 0, 0), 19 * s, "#ffffff", "Run anyway")
    dont = QRectF(box.right() - 180 * s, box.bottom() - 80 * s, 140 * s, 48 * s)
    p.setBrush(QColor("#2b5797"))
    p.setPen(QPen(QColor("#ffffff"), 1.5))
    p.drawRect(dont)
    text(p, dont.adjusted(0, 12 * s, 0, 0), 19 * s, "#ffffff", "Don't run")
    p.restore()
    start = QPointF(box.center().x(), box.bottom() + 40 * s)
    first, second = more.center(), run.center()
    if t < 3.4:
        at = start + (first - start) * phase(t, 1.6, 1.4)
    else:
        at = first + (second - first) * phase(t, 4.6, 1.4)
    for click in (3.2, 6.2):
        if t >= click:
            ring = phase(t, click, 0.5)
            p.save()
            p.setOpacity(1 - ring)
            p.setPen(QPen(mp.ACCENT, 3 * s))
            p.drawEllipse(at, 8 * s + 36 * s * ring, 8 * s + 36 * s * ring)
            p.restore()
    cursor(p, at, 1.4 * s, 3.2 <= t < 3.45 or 6.2 <= t < 6.45)


def assistant(p, w, h, t, st):
    centre, _ = mp.stage(w, h)
    picture(p, st.wizard, centre, w * 0.5, opacity=phase(t, 0, 0.5))


def add_url(p, w, h, t, st):
    centre, width = mp.stage(w, h)
    picture(p, st.download_frame(int(t * mp.FPS), 0.2 + 0.4 * min(1, t / 9), 11.8e6),
            centre, width, opacity=phase(t, 0, 0.5))  # fmt: skip
    if t < 4.5:  # first the Add URL card, then the download running
        picture(p, st.add_file, centre, w * 0.42, opacity=1 - phase(t, 3.8, 0.7))


def browser_use(p, w, h, t, st):
    mp.video_button(p, w, h, t, st)


def pause_convert(p, w, h, t, st):
    centre, width = mp.stage(w, h)
    picture(p, st.dark_main, centre, width, opacity=phase(t, 0, 0.5))
    percent = min(100, max(0, int((t - 2.5) / 3.5 * 100)))
    if t >= 2.0:
        picture(p, st.converts[percent - percent % 5], centre + QPointF(0, 40),
                w * 0.4, opacity=phase(t, 2.0, 0.5))  # fmt: skip


def outro(p, w, h, t, st):
    mp.call_to_action(p, w, h, t, st)
    s = mp.scale_of(w, h)
    text(p, QRectF(0, h * 0.24 + 620 * s, w, 60 * s), 28 * s, "#cbd5e1",
         "Link in the description", opacity=phase(t, 2.2, 0.6))  # fmt: skip


Scene = mp.Scene
SCENES = [
    Scene(5.0, "", "", mp.intro),
    Scene(9.0, "1. Download", "github.com/Conditions-tech/SDM → Releases", github_page),
    Scene(9.0, "2. Install", "If SmartScreen warns you: More info → Run anyway", smartscreen),
    Scene(10.0, "3. Connect your browser", "Add to Chrome, then follow the three steps", assistant),
    Scene(9.0, "4. Download a file", "Add URL → paste the address → Download", add_url),
    Scene(
        9.0, "5. From the browser", "Downloads open in SDM; videos get the SDM button", browser_use
    ),  # fmt: skip
    Scene(8.0, "6. Pause, resume, convert", "Right-click a download for more", pause_convert),
    Scene(8.0, "", "", outro),
]


def main() -> int:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        print("ffmpeg is needed: winget install Gyan.FFmpeg", file=sys.stderr)
        return 1
    app = mp.QApplication(sys.argv[:1])
    app.setWindowIcon(mp.app_icon())
    mp.OUT.mkdir(parents=True, exist_ok=True)
    windows = mp.Windows(app, mp.OUT / "work-tutorial")
    studio = mp.Studio(windows)
    studio.wizard = wizard_image(app)
    dialog = mp.AddUrlDialog(default_folder=mp.FOLDER, previous_downloads=lambda u: [],
                             video_enabled=True)  # fmt: skip
    dialog.url_edit.setText("https://example.com/ubuntu-26.04-desktop-amd64.iso")
    dialog.resize(640, 10)
    dialog.show()
    app.processEvents()
    studio.add_file = dialog.grab().toImage()
    dialog.close()
    path = mp.OUT / f"sdm-{__version__}-tutorial-wide.mp4"
    mp.render(studio, 1920, 1080, path, ffmpeg, SCENES)
    print(f"Made {path} ({path.stat().st_size / 1e6:.1f} MB)")
    windows.close()
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)  # see make_promo.py: Qt's off-screen teardown crashed at exit
