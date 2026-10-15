"""Helpers for keys the engine listens to and keys it sends."""
import logging
import threading
import time
import traceback
from collections.abc import Callable

import keyboard

from zeroflow import ui


def wait_for_release(hotkey: str, timeout: float = 1.0) -> None:
    """Wait (briefly) until every key in `hotkey` ("shift+f3") is up, so keys we send
    next are not combined with ones the user is still holding."""
    keys = [k.strip() for k in hotkey.split("+")]
    deadline = time.monotonic() + timeout
    while any(keyboard.is_pressed(k) for k in keys) and time.monotonic() < deadline:
        time.sleep(0.02)


def run_async(fn: Callable[[], None]) -> Callable[[], None]:
    """Wrap a hotkey handler so it runs on its own daemon thread. Heavy handlers
    (LLM calls, key-sending) must never run on the keyboard listener thread —
    blocking it freezes the whole keyboard until they return, which is what forced
    the app restarts on Ctrl+F10/F11. Failures are logged, not just printed."""
    def run():
        try:
            fn()
        except Exception:
            logging.error(f"{fn.__name__} failed: {traceback.format_exc()}")
            print(f"{ui.C_ERR}❌ {fn.__name__} failed — details in flow_debug.log.{ui.C_RESET}")
            ui.update_console_title("ONLINE")
    return lambda: threading.Thread(target=run, daemon=True).start()
