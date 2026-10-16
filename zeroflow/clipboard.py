"""The clipboard: pasting text, copying the selection, and reading it for context —
always giving back what the user had on it.

Both halves drive the clipboard — the reader copies a selection, dictation pastes —
and each sequence runs under the engine-wide clipboard lock (zeroflow.signals), so
neither can land in the middle of the other, in either process layout.
"""
import ctypes
import re
import time

import keyboard
import pyperclip

from zeroflow.signals import clipboard_lock
from zeroflow.text import URL_PATTERN

VK_CONTROL = 0x11
VK_C = 0x43
KEYEVENTF_KEYUP = 0x0002
# Slow apps take a moment to put a copied selection on the clipboard: look this many
# times, this far apart (half a second in all) before deciding nothing was selected.
POLL_ATTEMPTS = 25
POLL_INTERVAL = 0.02


def paste_text(text: str, press_enter: bool = False) -> None:
    """Paste `text` at the cursor through the clipboard, then restore the clipboard."""
    with clipboard_lock():
        saved_clipboard = pyperclip.paste()
        try:
            pyperclip.copy(text)
            time.sleep(0.04)
            keyboard.send('ctrl+v')
            # Give slow apps time to read the clipboard before we restore it — restoring
            # too early makes them paste the *old* clipboard contents instead.
            time.sleep(0.15)
            if press_enter:
                keyboard.send('enter')
        finally:
            # Even when a step above fails: the dictation must not replace what the
            # user had on the clipboard.
            pyperclip.copy(saved_clipboard)


def copy_selection(select: str | None = None) -> str | None:
    """The text selected in the focused app, or None if nothing is selected.

    Windows has no "read the selection" API that works everywhere, so the selection
    is copied with a synthetic Ctrl+C and read back. `select` is keys to send first
    ("shift+home" selects back to the start of the line). Used by F4 (read aloud) and
    Shift+F3 (fix the line); the caller makes sure its own hotkey is released first,
    or the Ctrl+C is combined with it."""
    with clipboard_lock():
        saved_clipboard = pyperclip.paste()
        try:
            pyperclip.copy("")                   # so a failed copy reads as empty, not as stale text
            time.sleep(POLL_INTERVAL)
            if select:
                keyboard.send(select)
                time.sleep(POLL_INTERVAL)
            _press_copy()
            for _ in range(POLL_ATTEMPTS):
                time.sleep(POLL_INTERVAL)
                text = pyperclip.paste().strip()
                if text:
                    return text
            return None
        finally:
            pyperclip.copy(saved_clipboard)


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
            return re.sub(URL_PATTERN, '', pyperclip.paste())[:500]
    except Exception:
        return ""
