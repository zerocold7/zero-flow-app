"""Hotkey capture for the Settings window: "press a key", and the check on what was pressed.

`check` refuses keys that must not be taken (Esc always cancels; Windows-key combinations
belong to Windows), reports a clash with another of the user's own keys, and warns about
keys browsers and Office use. The window cannot see other programs' keys, and says so.
"""
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLineEdit

CANNOT_SEE_OTHER_APPS = ("Zero- Flow can only check this key against its own. It cannot see "
                         "the keys other apps use; if one of them stops working, pick another key here.")

MODIFIERS = ("ctrl", "alt", "shift", "windows")
_WINDOWS_NAMES = {"win", "windows", "left windows", "right windows", "meta", "cmd", "super"}
_MODIFIER_NAMES = {"ctrl", "control", "left ctrl", "right ctrl", "alt", "left alt", "right alt",
                   "alt gr", "shift", "left shift", "right shift"} | _WINDOWS_NAMES
CANCEL_KEY = "esc"
WARN_KEYS = {"f5": "Browsers refresh the page with F5.",
             "f7": "Office checks spelling with F7."}

_SPECIAL = {Qt.Key_Escape: "esc", Qt.Key_Space: "space", Qt.Key_Tab: "tab",
            Qt.Key_Return: "enter", Qt.Key_Enter: "enter", Qt.Key_Backspace: "backspace",
            Qt.Key_Delete: "delete", Qt.Key_Insert: "insert", Qt.Key_Home: "home",
            Qt.Key_End: "end", Qt.Key_PageUp: "page up", Qt.Key_PageDown: "page down",
            Qt.Key_Left: "left", Qt.Key_Right: "right", Qt.Key_Up: "up", Qt.Key_Down: "down",
            Qt.Key_Pause: "pause", Qt.Key_ScrollLock: "scroll lock", Qt.Key_Print: "print screen"}
_PURE_MODIFIERS = (Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_AltGr,
                   Qt.Key_CapsLock)


@dataclass
class Verdict:
    level: str            # "ok", "warn", "clash" or "refused"
    reason: str = ""
    other: str = ""       # the shown name of the key it clashes with


def _parts(key: str) -> list[str]:
    return [p.strip() for p in key.lower().split("+") if p.strip()]


def _same_chord(a: str, b: str) -> bool:
    return sorted(_parts(a)) == sorted(_parts(b))


def check(key: str, assigned: dict[str, str], own_name: str) -> Verdict:
    """`assigned` maps each key's shown name ("Action · Fix line") to its key; `own_name`
    is the one being set, which never clashes with itself."""
    parts = _parts(key)
    if not parts:
        return Verdict("refused", "Press a key.")
    if all(p in _MODIFIER_NAMES for p in parts):
        return Verdict("refused", "A key like Ctrl or Shift needs another key with it.")
    import keyboard
    try:
        keyboard.parse_hotkey("+".join(parts))
    except (ValueError, KeyError):
        return Verdict("refused", f"Windows does not know a key called “{key}”.")
    if any(p in _WINDOWS_NAMES for p in parts):
        return Verdict("refused", "Key combinations with the Windows key belong to Windows.")
    if parts == [CANCEL_KEY]:
        return Verdict("refused", "Esc always cancels a recording and silences the Reader, "
                                  "so it cannot be used for anything else.")
    for name, other in assigned.items():
        if name != own_name and _same_chord(key, other):
            return Verdict("clash", f"That key is already {name}.", other=name)
    if len(parts) == 1 and parts[0] in WARN_KEYS:
        return Verdict("warn", WARN_KEYS[parts[0]] + " It will work here, but not there.")
    return Verdict("ok")


def key_from_event(key: int, modifiers) -> str | None:
    """The keyboard library's name for a Qt key press; None for a modifier on its own."""
    if key in _PURE_MODIFIERS or key == 0:
        return None
    if Qt.Key_F1 <= key <= Qt.Key_F24:
        name = f"f{key - Qt.Key_F1 + 1}"
    elif key in _SPECIAL:
        name = _SPECIAL[key]
    elif 0x20 < key < 0x7F:
        name = chr(key).lower()
    else:
        return None
    held = [m for m, flag in (("ctrl", Qt.ControlModifier), ("alt", Qt.AltModifier),
                              ("shift", Qt.ShiftModifier), ("windows", Qt.MetaModifier))
            if modifiers & flag]
    return "+".join(held + [name])


class HotkeyEdit(QLineEdit):
    """A box that takes the next key pressed in it."""
    captured = Signal(str)        # a key that was accepted
    judged = Signal()             # every press, accepted or not: read `verdict`

    def __init__(self, own_name: str, assigned: dict[str, str], current: str = ""):
        super().__init__(current)
        self.own_name, self.assigned, self.key = own_name, assigned, current
        self.verdict = Verdict("ok")
        self.setReadOnly(True)
        self.setPlaceholderText("Press a key")

    def keyPressEvent(self, event) -> None:
        pressed = key_from_event(event.key(), event.modifiers())
        if pressed is None:
            return                                # a modifier alone: wait for the real key
        self.verdict = check(pressed, self.assigned, self.own_name)
        self.judged.emit()
        if self.verdict.level in ("ok", "warn"):
            self.key = pressed
            self.setText(pressed)
            self.captured.emit(pressed)

    def message_text(self) -> str:
        return self.verdict.reason
