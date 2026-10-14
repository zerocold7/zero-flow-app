"""
Grab whatever text is highlighted in the focused app — through the engine's shared
copy routine (zeroflow.clipboard.copy_selection), which saves and restores the
user's clipboard: the reader must not be the one component that quietly eats it.
"""
import time

import keyboard

from zeroflow.clipboard import POLL_INTERVAL, copy_selection


def capture_highlighted_text(release_key=None):
    """Copy the current selection and return it, or None if nothing was selected.

    `release_key` is the hotkey that triggered the capture: it has to be released
    before the synthetic Ctrl+C, or Windows sees it still held and the copy is sent
    to the wrong place.
    """
    if release_key:
        keyboard.release(release_key)
        time.sleep(POLL_INTERVAL)
    return copy_selection()
