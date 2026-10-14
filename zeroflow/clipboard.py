"""Pasting text, and reading the clipboard, without losing what the user had on it."""
import re
import time

import keyboard
import pyperclip

from zeroflow.signals import clipboard_lock
URL_PATTERN = re.compile(r'https?://\S+|www\.\S+')


def paste_text(text, press_enter=False):
    """Paste `text` at the cursor through the clipboard, then restore the clipboard."""
    # Hold the clipboard for the whole save/paste/restore cycle so the reader cannot
    # copy a selection into the middle of it, in either process layout.
    with clipboard_lock():
        saved_clipboard = pyperclip.paste()
        pyperclip.copy(text)
        time.sleep(0.04)
        keyboard.send('ctrl+v')
        # Give slow apps time to read the clipboard before we restore it — restoring
        # too early makes them paste the *old* clipboard contents instead.
        time.sleep(0.15)
        if press_enter:
            keyboard.send('enter')
        pyperclip.copy(saved_clipboard)          # restore the user's clipboard


def read_clipboard_context():
    """The clipboard, minus URLs and capped, as background for the Polish prompt."""
    try:
        # Under the lock, so an injection still in flight is not mistaken for context.
        with clipboard_lock():
            return re.sub(URL_PATTERN, '', pyperclip.paste())[:500]
    except Exception:
        return ""
