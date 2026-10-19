"""Entry point of the installed sdm-bridge-host.exe, which Chrome starts (PyInstaller, M10)."""

import sys

from sdm.bridge.host import main

sys.exit(main())
