"""Dictation on / Reader on. Each half can be switched off at run time, which frees its
memory (a half's `stop` unloads its models); with both off the Engine is Paused: it stays
in the tray holding no models and no keys.

`Halves` knows nothing about Whisper or the Reader's process: it is given two objects
with `running`, `start()` and `stop()`, so the logic is testable. The real ones are in
zeroflow/supervisor.py. `save(name, value)` records the choice for the next start.
"""
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal


class Halves(QObject):
    state_changed = Signal(str)       # "active" or "paused"
    problem = Signal(str)             # a half could not start
    changed = Signal()                # either half switched on or off

    def __init__(self, dictation, reader, save: Callable[[str, bool], None]):
        super().__init__()
        self._dictation, self._reader, self._save = dictation, reader, save
        self._last = self.state

    @property
    def dictation_on(self) -> bool:
        return bool(self._dictation.running)

    @property
    def reader_on(self) -> bool:
        return bool(self._reader.running)

    @property
    def state(self) -> str:
        return "active" if self.dictation_on or self.reader_on else "paused"

    def set_dictation(self, on: bool) -> None:
        self._switch(self._dictation, "DICTATION_ON", "Dictation", on)

    def set_reader(self, on: bool) -> None:
        self._switch(self._reader, "READER_ON", "The Reader", on)

    def _switch(self, half, setting: str, label: str, on: bool) -> None:
        if bool(half.running) == on:
            return
        try:
            (half.start if on else half.stop)()
        except Exception as e:
            self.problem.emit(f"{label} could not be turned {'on' if on else 'off'}: {e}")
            return
        self._save(setting, on)
        self.changed.emit()
        if self.state != self._last:
            self._last = self.state
            self.state_changed.emit(self.state)
