"""One recording: its audio, and whether it was stopped or cancelled."""
import sys
import threading

import numpy as np

from zeroflow import ui


class Capture:
    """One recording: its mode, its audio, and whether it was stopped or cancelled.

    Nothing here is shared with the next recording, which can start the moment this
    one is stopped — while this one's microphone is still closing."""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self._chunks = []
        self.stopped = threading.Event()
        self.cancelled = False

    def callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        """sounddevice callback: keep the audio and draw a live level meter."""
        if self.stopped.is_set():
            return
        self._chunks.append(indata.copy())
        level = int(min(np.linalg.norm(indata) * 10, 20))
        bars = "|" * level + " " * (20 - level)
        sys.stdout.write(f"\r{ui.C_ACCENT}[{ui.C_GOOD}{bars}{ui.C_ACCENT}] Capturing Voice Data...{ui.C_RESET}")
        sys.stdout.flush()

    def stop(self, cancel: bool = False) -> None:
        self.cancelled = self.cancelled or cancel
        self.stopped.set()

    def audio(self) -> np.ndarray | None:
        """Everything captured, as one array, or None if nothing was."""
        return np.concatenate(self._chunks, axis=0) if self._chunks else None
