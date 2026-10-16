"""Shared pytest setup."""

import os

# Draw Qt windows off-screen: tests never pop up windows and also run without a desktop.
# This must be set before pytest-qt creates the QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
