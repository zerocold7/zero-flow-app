"""The overlay (zeroflow/overlay.py): a pill at the bottom centre that never takes focus,
lets clicks pass through and stays on top. Logic, not pixels (pytest-qt, offscreen).

The offscreen platform activates every window it shows (except tooltips), so the focus
test below only proves anything because the overlay is a tooltip-type window. The real
Win32 styles are checked in a second process on the real desktop platform."""
import os
import subprocess
import sys
import threading

import pytest
from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import QApplication, QLineEdit

from zeroflow.overlay import Overlay, UiBridge, STATES


@pytest.fixture
def overlay(qtbot):
    pill = Overlay()
    qtbot.addWidget(pill)
    return pill


def test_it_is_a_tool_window_that_stays_on_top_and_ignores_input(overlay):
    flags = overlay.windowFlags()
    assert flags & Qt.WindowStaysOnTopHint
    assert flags & Qt.FramelessWindowHint
    assert overlay.windowType() == Qt.ToolTip   # never activated, no taskbar entry
    assert flags & Qt.WindowDoesNotAcceptFocus
    assert flags & Qt.WindowTransparentForInput  # clicks pass through
    assert overlay.testAttribute(Qt.WA_ShowWithoutActivating)
    assert overlay.testAttribute(Qt.WA_TransparentForMouseEvents)
    assert overlay.focusPolicy() == Qt.NoFocus


@pytest.mark.parametrize("state", STATES)
def test_showing_a_state_never_moves_focus(qtbot, overlay, state):
    """The point of the whole overlay: dictation types into another program, and a
    window that stole focus would send the words to the pill instead."""
    other = QLineEdit()
    qtbot.addWidget(other)
    other.show()
    other.activateWindow()
    other.setFocus()
    qtbot.waitUntil(lambda: QApplication.activeWindow() is other)

    overlay.show_state(state)
    qtbot.wait(50)

    assert overlay.isVisible()
    # (not overlay.isActiveWindow(): Qt reports a parentless Tool window as active
    # whenever the application is, so that call says nothing here.)
    assert QApplication.activeWindow() is other
    assert QApplication.activeWindow() is not overlay
    assert QApplication.focusWidget() is other


def test_the_four_states_and_nothing_else(overlay):
    assert STATES == ("recording", "transcribing", "ai", "reading")
    overlay.show_state("ai")
    assert overlay.state == "ai"
    with pytest.raises(ValueError):
        overlay.show_state("dancing")
    assert overlay.state == "ai"                # the bad call changed nothing


def test_the_level_meter_is_kept_between_0_and_1(overlay):
    overlay.show_state("recording")
    for given, kept in [(0.4, 0.4), (-3, 0.0), (7, 1.0)]:
        overlay.set_level(given)
        assert overlay.level == kept


def test_hiding_clears_the_state(overlay):
    overlay.show_state("recording")
    overlay.hide_overlay()
    assert not overlay.isVisible()
    assert overlay.state is None


def test_it_sits_at_the_bottom_centre_of_the_screen(qtbot, overlay):
    overlay.show_state("recording")
    screen = overlay.screen().availableGeometry()
    middle = overlay.geometry().center().x()
    assert abs(middle - screen.center().x()) <= 1
    assert overlay.geometry().bottom() > screen.center().y()


def test_a_worker_thread_reaches_it_only_through_a_signal(qtbot, overlay):
    """ADR 0001: hook and worker threads never touch widgets; the slot must run on the
    main thread even when the signal is emitted from another."""
    bridge = UiBridge()
    ran_on = []
    bridge.status.connect(lambda state: ran_on.append(QThread.currentThread()))
    bridge.status.connect(overlay.show_state)

    worker = threading.Thread(target=lambda: bridge.status.emit("transcribing"))
    worker.start()
    worker.join()
    qtbot.waitUntil(lambda: overlay.state == "transcribing")
    assert ran_on == [QApplication.instance().thread()]


REAL_WINDOW = """
import ctypes, sys
from PySide6.QtWidgets import QApplication
from zeroflow.overlay import Overlay
app = QApplication([])
pill = Overlay()
pill.show_state("recording")
app.processEvents()
style = ctypes.windll.user32.GetWindowLongW(int(pill.winId()), -20)
print(style)
"""
WS_EX_TRANSPARENT, WS_EX_NOACTIVATE, WS_EX_TOPMOST = 0x20, 0x08000000, 0x8


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 window styles")
def test_the_real_window_is_not_activated_passes_clicks_and_stays_on_top():
    env = {k: v for k, v in os.environ.items() if k != "QT_QPA_PLATFORM"}
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    run = subprocess.run([sys.executable, "-c", REAL_WINDOW], cwd=root, env=env,
                         capture_output=True, text=True, timeout=60)
    style = int(run.stdout.strip().splitlines()[-1])
    assert style & WS_EX_NOACTIVATE
    assert style & WS_EX_TRANSPARENT
    assert style & WS_EX_TOPMOST


def test_the_pill_names_the_mode_the_recording_started_in(overlay):
    """The key that starts a recording decides its Mode, whichever key stops it; the pill
    says which one is running."""
    overlay.show_state("recording")
    overlay.set_detail("Arabic · Polish")
    assert overlay.detail == "Arabic · Polish"
    overlay.hide_overlay()
    assert overlay.detail == ""


def test_starting_a_recording_announces_its_mode(qtbot):
    from unittest import mock

    from zeroflow import engine
    bridge = UiBridge()
    with mock.patch.object(engine.ui, "bridge", bridge), \
         mock.patch.object(engine.ui, "play_tone"), mock.patch("builtins.print"), \
         qtbot.waitSignal(bridge.detail, timeout=500) as seen:
        engine._started_feedback("ar_polish")
    assert seen.args == ["Arabic · Polish"]
