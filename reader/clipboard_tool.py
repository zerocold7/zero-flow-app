"""
Grab whatever text is highlighted in the focused app.

Windows has no "read the selection" API that works everywhere, so the selection is
copied with a synthetic Ctrl+C and read back off the clipboard. The user's clipboard
is saved and restored afterwards — the dictation half snapshots the clipboard for
LLM context and restores it around every injection, and the reader must not be the
one component that quietly eats it.
"""
import ctypes
import time

import keyboard
import pyperclip

VK_CONTROL = 0x11
VK_C = 0x43
KEYEVENTF_KEYUP = 0x0002

POLL_ATTEMPTS = 25
POLL_INTERVAL = 0.02


def capture_highlighted_text(release_key=None, restore_clipboard=True):
    """Copy the current selection and return it, or None if nothing was selected.

    `release_key` is the hotkey that triggered the capture: it has to be released
    before the synthetic Ctrl+C, or Windows sees it still held and the copy is sent
    to the wrong place.
    """
    if release_key:
        keyboard.release(release_key)
        time.sleep(POLL_INTERVAL)

    saved_clipboard = pyperclip.paste()
    try:
        pyperclip.copy("")                       # so a failed copy reads as empty, not as stale text
        time.sleep(POLL_INTERVAL)

        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_C, 0, 0, 0)
        time.sleep(POLL_INTERVAL)
        ctypes.windll.user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

        for _ in range(POLL_ATTEMPTS):           # slow apps take a moment to fill the clipboard
            time.sleep(POLL_INTERVAL)
            text = pyperclip.paste().strip()
            if text:
                return text
        return None
    finally:
        if restore_clipboard:
            pyperclip.copy(saved_clipboard)
