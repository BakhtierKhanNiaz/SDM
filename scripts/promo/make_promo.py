"""Make SDM's promotional video from SDM's own windows.

    uv run python scripts/promo/make_promo.py        # dist\\promo\\sdm-<version>-wide/-tall.mp4
    uv run python scripts/promo/make_promo.py tall   # just one of them (about 5 minutes each)

Every frame is drawn with Qt: the download list, Add URL and Convert are SDM's real windows
(off-screen, with sample downloads in C:\\Users\\you\\Downloads, so no real user name shows),
animated frame by frame; ffmpeg (installed separately, as for SDM's converter) turns the frames
into MP4 (H.264). Wide 1920x1080 for YouTube, LinkedIn and Facebook; tall 1080x1920 for
Instagram and Facebook Reels. No sound: social videos play muted at first, and no music means
no copyright question. Run it again for each release: the version comes from SDM.
"""

import math
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:\\Windows\\Fonts")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)
from PySide6.QtSvg import QSvgRenderer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from sdm import __version__  # noqa: E402
from sdm.bridge.protocol import DownloadRequest  # noqa: E402
from sdm.core.downloads import BrowserContext  # noqa: E402
from sdm.media.ffmpeg import find_ffmpeg  # noqa: E402
from sdm.storage.database import DownloadStore  # noqa: E402
from sdm.ui.add_url_dialog import AddUrlDialog  # noqa: E402
from sdm.ui.controller import DownloadController  # noqa: E402
from sdm.ui.convert_dialog import ConvertDialog  # noqa: E402
from sdm.ui.icons import app_icon  # noqa: E402
from sdm.ui.main_window import MainWindow  # noqa: E402
from sdm.ui.theme import apply_theme  # noqa: E402

FPS = 30
FOLDER = Path(r"C:\Users\you\Downloads")  # shown in the windows: no real user name
OUT = ROOT / "dist" / "promo"
REPO = "github.com/Conditions-tech/SDM"
ACCENT = QColor("#38bdf8")


# ----- easing and drawing helpers -----


def ease(t: float) -> float:
    """0..1 -> 0..1, fast then gentle (ease-out cubic)."""
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


def phase(t: float, start: float, length: float) -> float:
    return ease((t - start) / length)


def text(p: QPainter, rect: QRectF, size: float, colour, s: str, *, weight=QFont.Weight.Normal,
         align=Qt.AlignmentFlag.AlignHCenter, opacity: float = 1.0) -> None:  # fmt: skip
    font = QFont("Segoe UI")
    font.setPixelSize(max(1, int(size)))
    font.setWeight(weight)
    p.save()
    p.setOpacity(opacity)
    p.setFont(font)
    p.setPen(QColor(colour))
    p.drawText(rect, align | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, s)
    p.restore()


def picture(p: QPainter, image: QImage, centre: QPointF, width: float, *, opacity=1.0,
            radius=16.0) -> QRectF:  # fmt: skip
    """A window picture with rounded corners and a soft shadow, `width` wide."""
    height = width * image.height() / image.width()
    rect = QRectF(centre.x() - width / 2, centre.y() - height / 2, width, height)
    p.save()
    p.setOpacity(opacity)
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(6):  # shadow
        grow = 4 + i * 5
        p.setBrush(QColor(0, 0, 0, 16))
        p.drawRoundedRect(
            rect.adjusted(-grow, -grow + 10, grow, grow + 10), radius + grow, radius + grow
        )
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    p.setClipPath(path)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawImage(rect, image)
    p.setClipping(False)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 50), 1.5))
    p.drawPath(path)
    p.restore()
    return rect


def background(p: QPainter, w: int, h: int, t: float) -> None:
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor("#0b1120"))
    g.setColorAt(1, QColor("#1e1b4b"))
    p.fillRect(0, 0, w, h, g)
    # a slow glow that drifts, so still scenes don't look frozen
    x = w * (0.3 + 0.2 * math.sin(t * 0.35))
    y = h * (0.35 + 0.15 * math.cos(t * 0.27))
    glow = QRadialGradient(QPointF(x, y), max(w, h) * 0.55)
    glow.setColorAt(0, QColor(56, 189, 248, 46))
    glow.setColorAt(1, QColor(56, 189, 248, 0))
    p.fillRect(0, 0, w, h, glow)


def cursor(p: QPainter, at: QPointF, scale: float, pressed: bool = False) -> None:
    shape = QPolygonF([QPointF(0, 0), QPointF(0, 26), QPointF(7, 20), QPointF(12, 31),
                       QPointF(17, 29), QPointF(12, 18), QPointF(21, 18)])  # fmt: skip
    p.save()
    p.translate(at)
    p.scale(scale * (0.9 if pressed else 1), scale * (0.9 if pressed else 1))
    p.setPen(QPen(QColor("#111827"), 1.6))
    p.setBrush(QColor("#ffffff"))
    p.drawPolygon(shape)
    p.restore()


# ----- SDM's real windows -----


class Windows:
    """SDM's windows, off-screen, with sample downloads; pictures of them on request."""

    def __init__(self, app: QApplication, work: Path) -> None:
        self.app = app
        work.mkdir(parents=True, exist_ok=True)
        db = work / "promo.db"
        db.unlink(missing_ok=True)
        self.store = DownloadStore(db)
        self._sample_downloads()
        self.controller = DownloadController(self.store)
        self.window = MainWindow(self.controller, default_folder=FOLDER)
        self.window.resize(1280, 720)
        self.window.show()
        self.logo = QSvgRenderer(str(ROOT / "src" / "sdm" / "ui" / "assets" / "sdm.svg"))

    def _sample_downloads(self) -> None:
        def finished(name: str, category: str, size: int, checksum: bool = False) -> None:
            entry = self.store.add(f"https://example.com/{name}", str(FOLDER), category=category,
                                   context=BrowserContext(None, None))  # fmt: skip
            self.store.mark_downloading(entry.id)
            self.store.mark_completed(entry.id, path=str(FOLDER / name), size=size,
                                      verified_complete=True)  # fmt: skip
            self.store.set_file_info(entry.id, name, size)
            if checksum:
                self.store.set_checksum(entry.id, "a" * 64, "verified")

        finished("Holiday in Cox's Bazar.mp4", "Video", 734_003_200)
        finished("Rabindra Sangeet collection.mp3", "Music", 9_437_184)
        finished("python-3.14.7-amd64.exe", "Programs", 28_311_552, checksum=True)
        finished("Annual report 2026.pdf", "Documents", 2_097_152)
        running = self.store.add(
            "https://example.com/ubuntu.iso", str(FOLDER), category="Compressed"
        )
        self.store.mark_downloading(running.id)
        self.store.set_file_info(running.id, "ubuntu-26.04-desktop-amd64.iso", 6_200_000_000)
        self.running_id = running.id
        paused = self.store.add(
            "https://example.com/dataset.zip", str(FOLDER), category="Compressed"
        )
        self.store.set_file_info(paused.id, "dataset.zip", 1_500_000_000)
        self.store.mark_paused(paused.id)
        self.store.set_progress(paused.id, 600_000_000)

    def theme(self, dark: bool) -> None:
        apply_theme(self.app, "dark" if dark else "light")
        self.window.refresh_icons()
        self.app.processEvents()

    def main(self, *, progress: float = 0.4, speed: float = 11.8e6, select_running=True) -> QImage:
        total = 6_200_000_000
        received = int(total * progress)
        left = (total - received) / speed
        self.controller.model.set_live(self.running_id, received, total, speed, left, 8)
        if select_running:
            self.window.select_id(self.running_id)
        else:
            self.window.download_table.selectRow(0)
        self.app.processEvents()
        return self.window.grab().toImage()

    def add_url(self) -> QImage:
        dialog = AddUrlDialog(default_folder=FOLDER, previous_downloads=lambda url: [],
                              video_enabled=True)  # fmt: skip
        dialog.show_browser_request(DownloadRequest("https://video.example.com/watch?v=sdm",
                                                    source="video"))  # fmt: skip
        dialog.choose_video("1080p")
        dialog.resize(640, 10)
        dialog.show()
        self.app.processEvents()
        image = dialog.grab().toImage()
        dialog.close()
        return image

    def convert(self, percent: int) -> QImage:
        dialog = ConvertDialog(ffmpeg=["ffmpeg.exe"], source=FOLDER / "Holiday in Cox's Bazar.mp4")
        dialog.resize(620, 10)
        dialog.show()
        dialog.bar.setValue(percent)
        if percent >= 100:
            dialog.status_label.setText("Done: Holiday in Cox's Bazar.mp3")
            dialog.show_button.show()
        else:
            dialog.status_label.setText("Converting to Holiday in Cox's Bazar.mp3…")
            dialog.convert_button.setEnabled(False)
            dialog.close_button.setText("Cancel")
        self.app.processEvents()
        image = dialog.grab().toImage()
        dialog.close()
        return image

    def close(self) -> None:
        # The sample download is "running": without this, closing would ask "Quit?" in a
        # message box nobody can see (off-screen), and the script would wait forever.
        self.window.confirm_quit = lambda active: True
        self.window.close()
        self.store.close()


# ----- the browser scene (drawn, with SDM's button as the extension shows it) -----


def browser(p: QPainter, rect: QRectF, logo: QSvgRenderer, t: float, s: float) -> QRectF:
    """A browser window showing a video page; returns where SDM's button is."""
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#202124"))
    p.drawRoundedRect(rect, 14 * s, 14 * s)
    bar = QRectF(rect.x() + 16 * s, rect.y() + 14 * s, rect.width() - 32 * s, 34 * s)
    p.setBrush(QColor("#303134"))
    p.drawRoundedRect(bar, 17 * s, 17 * s)
    text(p, bar.adjusted(18 * s, 7 * s, 0, 0), 15 * s, "#bdc1c6", "video.example.com/watch?v=sdm",
         align=Qt.AlignmentFlag.AlignLeft)  # fmt: skip
    page = QRectF(rect.x(), rect.y() + 62 * s, rect.width(), rect.height() - 62 * s)
    p.setBrush(QColor("#0f0f0f"))
    p.drawRect(page)
    video = QRectF(page.x() + 30 * s, page.y() + 24 * s, page.width() - 60 * s,
                   (page.width() - 60 * s) * 9 / 16)  # fmt: skip
    g = QLinearGradient(video.topLeft(), video.bottomRight())
    g.setColorAt(0, QColor("#f97316"))
    g.setColorAt(0.55, QColor("#db2777"))
    g.setColorAt(1, QColor("#4c1d95"))
    p.setBrush(g)
    p.drawRoundedRect(video, 10 * s, 10 * s)
    # a sun and hills, so it reads as a video frame
    p.setBrush(QColor(255, 237, 213, 200))
    vw, vh = video.width(), video.height()
    sun = QPointF(video.center().x() + vw * 0.18, video.y() + vh * 0.42)
    p.drawEllipse(sun, vh * 0.13, vh * 0.13)
    hills = QPainterPath(QPointF(video.left(), video.bottom()))
    hills.cubicTo(QPointF(video.left() + vw * 0.3, video.bottom() - vh * 0.45),
                  QPointF(video.left() + vw * 0.6, video.bottom() - vh * 0.05),
                  QPointF(video.right(), video.bottom() - vh * 0.3))  # fmt: skip
    hills.lineTo(video.bottomRight())
    hills.closeSubpath()
    p.setBrush(QColor(30, 27, 75, 220))
    p.drawPath(hills)
    # the playing timeline
    line = QRectF(video.x() + 20 * s, video.bottom() - 22 * s, video.width() - 40 * s, 5 * s)
    p.setBrush(QColor(255, 255, 255, 80))
    p.drawRoundedRect(line, 2.5 * s, 2.5 * s)
    p.setBrush(QColor("#ef4444"))
    played = line.adjusted(0, 0, -line.width() * (1 - min(1.0, 0.25 + t * 0.03)), 0)
    p.drawRoundedRect(played, 2.5 * s, 2.5 * s)
    p.restore()
    # SDM's button, as video-button.js draws it: logo, "Download", and x
    appear = phase(t, 1.0, 0.5)
    button = QRectF(video.right() - 196 * s, video.y() + 12 * s, 150 * s, 38 * s)
    close = QRectF(button.right() + 4 * s, button.y(), 34 * s, 38 * s)
    p.save()
    p.setOpacity(appear)
    p.setPen(QPen(QColor(255, 255, 255, 64), 1.2 * s))
    p.setBrush(QColor(17, 24, 39, 235))
    p.drawRoundedRect(button, 9 * s, 9 * s)
    p.drawRoundedRect(close, 9 * s, 9 * s)
    logo.render(p, QRectF(button.x() + 12 * s, button.y() + 8 * s, 22 * s, 22 * s))
    text(p, button.adjusted(42 * s, 8 * s, 0, 0), 16 * s, "#ffffff", "Download",
         weight=QFont.Weight.DemiBold, align=Qt.AlignmentFlag.AlignLeft)  # fmt: skip
    text(p, close.adjusted(0, 8 * s, 0, 0), 15 * s, "#d1d5db", "\u2715")
    p.restore()
    return button


# ----- scenes -----


@dataclass
class Scene:
    seconds: float
    title: str
    subtitle: str
    draw: Callable[[QPainter, int, int, float, "Studio"], None]


class Studio:
    """Pictures prepared once, so drawing a frame is quick."""

    def __init__(self, windows: Windows) -> None:
        self.windows = windows
        self.logo = windows.logo
        windows.theme(dark=True)
        self.dark_main = windows.main(select_running=False)
        self.add_url = windows.add_url()
        self.converts = {p: windows.convert(p) for p in range(0, 101, 5)}
        windows.theme(dark=False)
        self.light_main = windows.main(select_running=False)
        windows.theme(dark=True)
        self._download_cache: dict[int, QImage] = {}

    def download_frame(self, frame: int, progress: float, speed: float) -> QImage:
        if frame not in self._download_cache:
            self._download_cache[frame] = self.windows.main(progress=progress, speed=speed)
        return self._download_cache[frame]


def stage(w: int, h: int) -> tuple[QPointF, float]:
    """Where a window picture goes, and how wide, below the caption."""
    if w > h:  # wide
        return QPointF(w / 2, h * 0.6), w * 0.66
    return QPointF(w / 2, h * 0.58), w * 0.92


def main_window_place(w: int, h: int, t: float, seconds: float) -> tuple[QPointF, float]:
    """The main window's place. On a tall (phone) frame it is shown much larger than the
    frame is wide, so it can be read, and pans slowly from its left side to its right."""
    centre, width = stage(w, h)
    if w > h:
        return centre, width
    width = w * 1.7
    overflow = width - w
    # starts on the sidebar, moves gently (slow at both ends), stops before the right edge
    x = min(1.0, max(0.0, (t - 0.8) / max(0.1, seconds - 1.4)))
    pan = (x * x * (3 - 2 * x)) * 0.6
    return QPointF(w / 2 + overflow / 2 - overflow * pan, centre.y()), width


def scale_of(w: int, h: int) -> float:
    return min(w, h) / 1080


def intro(p, w, h, t, st):
    s = scale_of(w, h)
    grow = phase(t, 0.0, 0.9)
    size = 260 * s * (0.6 + 0.4 * grow)
    p.save()
    p.setOpacity(grow)
    st.logo.render(p, QRectF(w / 2 - size / 2, h * 0.36 - size / 2, size, size))
    p.restore()
    text(p, QRectF(0, h * 0.36 + 170 * s, w, 140 * s), 110 * s, "#ffffff", "SDM",
         weight=QFont.Weight.Bold, opacity=phase(t, 0.6, 0.6))  # fmt: skip
    text(p, QRectF(0, h * 0.36 + 300 * s, w, 80 * s), 40 * s, "#cbd5e1",
         "Smart Download Manager for Windows", opacity=phase(t, 1.1, 0.6))  # fmt: skip
    text(p, QRectF(0, h * 0.36 + 360 * s, w, 60 * s), 30 * s, ACCENT, f"Version {__version__}",
         opacity=phase(t, 1.5, 0.6))  # fmt: skip


def downloading(p, w, h, t, st):
    centre, width = main_window_place(w, h, t, 6.0)
    frame = int(t * FPS)
    progress = 0.18 + 0.55 * min(1.0, t / 6.0)
    speed = 11.8e6 + 1.6e6 * math.sin(t * 2.3)
    image = st.download_frame(frame, progress, speed)
    zoom = 1 + 0.03 * phase(t, 0, 6)
    picture(p, image, centre + QPointF(0, 30 * (1 - phase(t, 0, 0.6))), width * zoom,
            opacity=phase(t, 0, 0.5))  # fmt: skip


def video_button(p, w, h, t, st):
    s = scale_of(w, h)
    centre, width = stage(w, h)
    height = width * 0.62
    rect = QRectF(centre.x() - width / 2, centre.y() - height / 2, width, height)
    p.save()
    p.setOpacity(phase(t, 0, 0.5))
    button = browser(p, rect, st.logo, t, width / 1280)
    p.restore()
    # the mouse moves to SDM's button and clicks it
    start = QPointF(rect.center().x() - width * 0.1, rect.bottom() - height * 0.2)
    target = button.center() + QPointF(-20 * s, 4 * s)
    move = phase(t, 1.7, 1.2)
    at = start + (target - start) * move
    pressed = 3.0 <= t < 3.25
    if t >= 3.0:
        ripple = phase(t, 3.0, 0.5)
        p.save()
        p.setOpacity(1 - ripple)
        p.setPen(QPen(ACCENT, 3 * s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(target, 10 * s + 40 * s * ripple, 10 * s + 40 * s * ripple)
        p.restore()
    if t < 3.6:
        cursor(p, at, 1.4 * s, pressed)
    # SDM answers: Add URL, already set to the video and the last quality
    if t >= 3.4:
        come = phase(t, 3.4, 0.6)
        dialog_width = min(w * 0.62, 860 * s) if w > h else w * 0.86
        picture(p, st.add_url, QPointF(w / 2, centre.y() + 40 * s * (1 - come)), dialog_width,
                opacity=come)  # fmt: skip


def organised(p, w, h, t, st):
    centre, width = main_window_place(w, h, t, 4.5)
    zoom = 1 + 0.05 * phase(t, 0, 4.5)
    picture(p, st.dark_main, centre, width * zoom, opacity=phase(t, 0, 0.5))


def converting(p, w, h, t, st):
    s = scale_of(w, h)
    centre, width = stage(w, h)
    percent = min(100, max(0, int((t - 0.6) / 3.0 * 100)))
    image = st.converts[min(100, percent - percent % 5)]
    dialog_width = min(w * 0.55, 900 * s) if w > h else w * 0.86
    picture(p, image, centre, dialog_width, opacity=phase(t, 0, 0.5))


def light_and_dark(p, w, h, t, st):
    centre, width = main_window_place(w, h, t, 3.5)
    mix = phase(t, 1.0, 1.4)
    picture(p, st.light_main, centre, width, opacity=1 - mix)
    picture(p, st.dark_main, centre, width, opacity=mix)


def call_to_action(p, w, h, t, st):
    s = scale_of(w, h)
    size = 200 * s
    top = h * 0.24
    p.save()
    p.setOpacity(phase(t, 0, 0.6))
    st.logo.render(p, QRectF(w / 2 - size / 2, top, size, size))
    p.restore()
    text(p, QRectF(0, top + 220 * s, w, 120 * s), 84 * s, "#ffffff", "Download SDM",
         weight=QFont.Weight.Bold, opacity=phase(t, 0.3, 0.6))  # fmt: skip
    text(p, QRectF(0, top + 330 * s, w, 70 * s), 38 * s, "#cbd5e1",
         "Free and open source · Windows 10 and 11", opacity=phase(t, 0.7, 0.6))  # fmt: skip
    pill_w, pill_h = 760 * s, 92 * s
    pill = QRectF(w / 2 - pill_w / 2, top + 430 * s, pill_w, pill_h)
    p.save()
    p.setOpacity(phase(t, 1.1, 0.6))
    p.setPen(Qt.PenStyle.NoPen)
    pulse = 0.5 + 0.5 * math.sin(t * 3)
    p.setBrush(QColor(56, 189, 248, int(40 + 50 * pulse)))
    p.drawRoundedRect(pill.adjusted(-8 * s, -8 * s, 8 * s, 8 * s), 54 * s, 54 * s)
    p.setBrush(ACCENT)
    p.drawRoundedRect(pill, 46 * s, 46 * s)
    p.restore()
    text(p, pill.adjusted(0, 22 * s, 0, 0), 40 * s, "#0b1120", REPO, weight=QFont.Weight.Bold,
         opacity=phase(t, 1.1, 0.6))  # fmt: skip
    text(p, QRectF(0, top + 560 * s, w, 60 * s), 30 * s, "#94a3b8",
         "Releases → SDM-Setup.exe", opacity=phase(t, 1.6, 0.6))  # fmt: skip


SCENES = [
    Scene(3.5, "", "", intro),
    Scene(
        6.0,
        "Download faster",
        "Big files over 8 connections at once, with pause and resume",
        downloading,
    ),  # fmt: skip
    Scene(
        6.0,
        "One click on any video",
        "The SDM button appears over videos in your browser",
        video_button,
    ),  # fmt: skip
    Scene(
        4.5,
        "Everything in order",
        "A sidebar, file types and colours show what's going on",
        organised,
    ),  # fmt: skip
    Scene(
        4.5,
        "Convert to MP3 or MP4",
        "Turn a video into music, or into an MP4 that plays anywhere",
        converting,
    ),  # fmt: skip
    Scene(3.5, "Light or dark", "SDM follows your Windows theme", light_and_dark),
    Scene(7.0, "", "", call_to_action),
]


def caption(p, w, h, scene: Scene, t: float) -> None:
    if not scene.title:
        return
    s = scale_of(w, h)
    top = h * (0.08 if w > h else 0.17)
    rise = 20 * s * (1 - phase(t, 0, 0.6))
    text(p, QRectF(60 * s, top + rise, w - 120 * s, 120 * s), 72 * s, "#ffffff", scene.title,
         weight=QFont.Weight.Bold, opacity=phase(t, 0, 0.6))  # fmt: skip
    text(p, QRectF(80 * s, top + 100 * s + rise, w - 160 * s, 120 * s), 34 * s, "#cbd5e1",
         scene.subtitle, opacity=phase(t, 0.25, 0.6))  # fmt: skip


def render(studio, w: int, h: int, path: Path, ffmpeg: Path, scenes=None) -> None:
    scenes = SCENES if scenes is None else scenes
    command = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
               "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-",
               "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
               "-movflags", "+faststart", str(path)]  # fmt: skip
    encoder = subprocess.Popen(command, stdin=subprocess.PIPE)  # noqa: S603 - fixed arguments
    frame = QImage(w, h, QImage.Format.Format_ARGB32)
    elapsed = 0.0
    for scene in scenes:
        frames = int(scene.seconds * FPS)
        for index in range(frames):
            t = index / FPS
            p = QPainter(frame)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            background(p, w, h, elapsed + t)
            scene.draw(p, w, h, t, studio)
            caption(p, w, h, scene, t)
            # fade in at the very start, and between scenes
            fade = min(1.0, t / 0.25, (scene.seconds - t) / 0.25)
            if fade < 1:
                p.fillRect(0, 0, w, h, QColor(11, 17, 32, int(255 * (1 - fade))))
            p.end()
            encoder.stdin.write(bytes(frame.constBits()))
        elapsed += scene.seconds
    encoder.stdin.close()
    if encoder.wait() != 0:
        raise SystemExit(f"ffmpeg couldn't make {path.name}")


def main() -> int:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        print("ffmpeg is needed: winget install Gyan.FFmpeg", file=sys.stderr)
        return 1
    app = QApplication(sys.argv[:1])
    app.setWindowIcon(app_icon())
    OUT.mkdir(parents=True, exist_ok=True)
    windows = Windows(app, OUT / "work")
    studio = Studio(windows)
    sizes = {"wide": (1920, 1080), "tall": (1080, 1920)}
    only = sys.argv[1:]  # e.g. "tall" to make just that one
    for name, (w, h) in sizes.items():
        if only and name not in only:
            continue
        path = OUT / f"sdm-{__version__}-{name}.mp4"
        render(studio, w, h, path, ffmpeg)
        print(f"Made {path} ({path.stat().st_size / 1e6:.1f} MB)")
    windows.close()
    return 0


if __name__ == "__main__":
    code = main()
    # Every file is written and closed by now. Tearing down Qt's off-screen windows at
    # interpreter exit crashed (Windows "fail-fast", seen 2026-10-26) after the videos were
    # complete, so this script ends the process directly instead.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
