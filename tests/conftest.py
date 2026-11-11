"""pytest set-up for the window tests (pytest-qt): no real screen, so Qt draws offscreen.
Set before anything imports PySide6."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
