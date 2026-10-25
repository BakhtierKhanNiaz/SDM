"""Make every SDM icon file from the one logo, src/sdm/ui/assets/sdm.svg (M13).

    uv run python scripts/make_icons.py

- src/sdm/ui/assets/sdm-<size>.png  the window and tray icon (16-256 px)
- packaging/sdm.ico                  SDM.exe, the helper and the installer (16-256 px in one file)
- extension/chrome/icons/sdm-<size>.png  the browser extension (16, 32, 48, 128 px)

Run it again after changing the SVG, and commit the results: the build and the tests use the
files, so they don't need Qt's SVG renderer.
"""

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "sdm" / "ui" / "assets" / "sdm.svg"
APP_SIZES = (16, 24, 32, 48, 64, 128, 256)
EXTENSION_SIZES = (16, 32, 48, 128)


def render(renderer: QSvgRenderer, size: int) -> bytes:
    """The logo as a PNG of size x size pixels."""
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data.data())


def ico(images: dict[int, bytes]) -> bytes:
    """A Windows .ico holding PNG images (supported since Windows Vista)."""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, payload = b"", b""
    for size, png in sorted(images.items()):
        side = size % 256  # 0 means 256
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(png), offset)
        payload += png
        offset += len(png)
    return header + entries + payload


def main() -> int:
    app = QGuiApplication(sys.argv[:1])  # noqa: F841 - Qt needs it to render
    renderer = QSvgRenderer(str(SOURCE))
    if not renderer.isValid():
        print(f"Can't read {SOURCE}", file=sys.stderr)
        return 1
    pngs = {size: render(renderer, size) for size in sorted({*APP_SIZES, *EXTENSION_SIZES})}
    assets = SOURCE.parent
    for size in APP_SIZES:
        (assets / f"sdm-{size}.png").write_bytes(pngs[size])
    (ROOT / "packaging" / "sdm.ico").write_bytes(ico({s: pngs[s] for s in APP_SIZES}))
    icons = ROOT / "extension" / "chrome" / "icons"
    icons.mkdir(exist_ok=True)
    for size in EXTENSION_SIZES:
        (icons / f"sdm-{size}.png").write_bytes(pngs[size])
    print(
        f"Made {len(APP_SIZES)} app PNGs, packaging/sdm.ico, {len(EXTENSION_SIZES)} extension PNGs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
