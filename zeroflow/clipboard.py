"""The clipboard: pasting text, copying the selection, and reading it for context —
always giving back what the user had on it: every format, an image or copied files
too (zeroflow.win_clipboard), with the engine's own text kept out of clipboard history.

Both halves drive the clipboard — the reader copies a selection, dictation pastes —
and each sequence runs under the engine-wide clipboard lock (zeroflow.signals), so
neither can land in the middle of the other, in either process layout.
"""
import ctypes
import logging
import re
import threading
import time

import keyboard

from zeroflow import win_clipboard as system_clipboard
from zeroflow.win_clipboard import ClipboardBusy
from zeroflow.signals import clipboard_lock
from zeroflow.text import URL_PATTERN

VK_CONTROL = 0x11
VK_C = 0x43
KEYEVENTF_KEYUP = 0x0002
# Slow apps take a moment to put a copied selection on the clipboard: look this many
# times, this far apart (half a second in all) before deciding nothing was selected.
POLL_ATTEMPTS = 25
POLL_INTERVAL = 0.02
# Another app may keep the clipboard open past the paste: try to put the user's
# clipboard back this many more times, this far apart.
RESTORE_ATTEMPTS = 10
RESTORE_RETRY_SECONDS = 1.0


def paste_text(text: str) -> None:
    """Paste `text` at the cursor through the clipboard, then restore the clipboard."""
    with clipboard_lock():
        saved_clipboard = system_clipboard.snapshot()
        try:
            system_clipboard.set_text(text)
            time.sleep(0.04)
            keyboard.send('ctrl+v')
            # Give slow apps time to read the clipboard before we restore it — restoring
            # too early makes them paste the *old* clipboard contents instead.
            time.sleep(0.15)
        finally:
            # Even when a step above fails: the dictation must not replace what the
            # user had on the clipboard.
            _restore(saved_clipboard)


def _restore(saved) -> None:
    """Put the user's clipboard back — now, or, if another app is holding the clipboard,
    a little later on a thread of its own. Raised, the busy clipboard used to throw the
    snapshot away and fail a dictation that had already been pasted."""
    try:
        system_clipboard.restore(saved)
    except ClipboardBusy:
        logging.warning("The clipboard was busy after the paste; restoring it shortly.")
        threading.Thread(target=_restore_later, args=(saved,), daemon=True).start()


def _restore_later(saved) -> None:
    for _ in range(RESTORE_ATTEMPTS):
        time.sleep(RESTORE_RETRY_SECONDS)
        try:
            with clipboard_lock():
                system_clipboard.restore(saved)
            return
        except ClipboardBusy:
            continue
    logging.error("The clipboard stayed busy; what was on it could not be put back.")


def copy_selection(select: str | None = None) -> str | None:
    """The text selected in the focused app, or None if nothing is selected.

    Windows has no "read the selection" API that works everywhere, so the selection
    is copied with a synthetic Ctrl+C and read back. `select` is keys to send first
    ("shift+home" selects back to the start of the line). Used by F4 (read aloud) and
    Shift+F3 (fix the line); the caller makes sure its own hotkey is released first,
    or the Ctrl+C is combined with it."""
    with clipboard_lock():
        saved_clipboard = system_clipboard.snapshot()
        try:
            system_clipboard.clear()             # so a failed copy reads as empty, not as stale text
            time.sleep(POLL_INTERVAL)
            if select:
                keyboard.send(select)
                time.sleep(POLL_INTERVAL)
            _press_copy()
            for _ in range(POLL_ATTEMPTS):
                time.sleep(POLL_INTERVAL)
                text = system_clipboard.get_text().strip()
                if text:
                    return text
            return None
        finally:
            _restore(saved_clipboard)


def _press_copy() -> None:
    """Ctrl+C, held for a moment: some apps miss a press and release sent together."""
    ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
    ctypes.windll.user32.keybd_event(VK_C, 0, 0, 0)
    time.sleep(POLL_INTERVAL)
    ctypes.windll.user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
    ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def read_clipboard_context() -> str:
    """The clipboard, minus URLs and capped, as background for the Polish prompt."""
    try:
        # Under the lock, so an injection still in flight is not mistaken for context.
        with clipboard_lock():
            return re.sub(URL_PATTERN, '', system_clipboard.get_text())[:500]
    except Exception:
        return ""
