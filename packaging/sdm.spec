# PyInstaller build of SDM (M10, ADR-0018). Build with: uv run python scripts/build_release.py
#
# One folder, two programs sharing the same libraries:
#   SDM.exe              the window (no console)
#   sdm-bridge-host.exe  the native messaging host Chrome starts (console: it talks over stdin
#                        and stdout; Chrome starts it hidden). It never loads Qt.
# Qt's DLLs stay separate files in the folder, as Qt's LGPL licence expects.
import os

from PyInstaller.utils.hooks import copy_metadata

HERE = SPECPATH  # noqa: F821 - provided by PyInstaller
SRC = os.path.join(HERE, "..", "src")
metadata = copy_metadata("sdm")  # so sdm.__version__ works in the frozen app
ICON = os.path.join(HERE, "sdm.ico")  # SDM's logo (M13), made by scripts/make_icons.py
# The window's logo PNGs, where sdm.ui.icons looks for them.
assets = [(os.path.join(SRC, "sdm", "ui", "assets", "*.png"), os.path.join("sdm", "ui", "assets"))]

app = Analysis(  # noqa: F821
    [os.path.join(HERE, "entry_sdm.py")],
    pathex=[SRC],
    datas=metadata + assets,
    excludes=["tkinter", "unittest", "pydoc", "test"],
)
host = Analysis(  # noqa: F821
    [os.path.join(HERE, "entry_host.py")],
    pathex=[SRC],
    datas=metadata,
    excludes=["tkinter", "unittest", "pydoc", "test", "PySide6", "shiboken6", "aiohttp"],
)

app_exe = EXE(  # noqa: F821
    PYZ(app.pure),  # noqa: F821
    app.scripts,
    [],
    exclude_binaries=True,
    name="SDM",
    console=False,
    icon=ICON,
    upx=False,
)
host_exe = EXE(  # noqa: F821
    PYZ(host.pure),  # noqa: F821
    host.scripts,
    [],
    exclude_binaries=True,
    name="sdm-bridge-host",
    console=True,
    icon=ICON,
    upx=False,
)
COLLECT(  # noqa: F821
    app_exe,
    app.binaries,
    app.datas,
    host_exe,
    host.binaries,
    host.datas,
    name="SDM",
    upx=False,
)
