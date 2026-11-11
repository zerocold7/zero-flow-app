"""Hotkey capture (zeroflow/hotkey_capture.py): "press a key" in the Settings window.
The check refuses reserved keys, reports clashes with the user's own keys, and warns on
keys browsers and Office use. `assigned` maps each key's shown name to its key."""
import pytest
from PySide6.QtCore import Qt

from zeroflow.hotkey_capture import CANNOT_SEE_OTHER_APPS, HotkeyEdit, check

ASSIGNED = {"Raw · English": "f5", "Action · Fix line": "shift+f3",
            "Reader · Read the selection": "f4"}


@pytest.mark.parametrize("key", ["esc", "Esc", "win+r", "windows+shift+s",
                                 "left windows+e", "ctrl+win+left"])
def test_reserved_keys_are_refused(key):
    verdict = check(key, ASSIGNED, "Polish · English")
    assert verdict.level == "refused"
    assert verdict.reason


@pytest.mark.parametrize("key", ["", "ctrl", "shift+alt", "f55", "not a key"])
def test_nothing_usable_is_refused(key):
    assert check(key, ASSIGNED, "Polish · English").level == "refused"


def test_a_clash_names_the_other_key_it_would_take():
    verdict = check("shift+f3", ASSIGNED, "Action · Tidy vocabulary")
    assert verdict.level == "clash"
    assert verdict.other == "Action · Fix line"
    assert "Fix line" in verdict.reason


def test_a_clash_ignores_case_and_order():
    verdict = check("Alt+Ctrl+R", {"Raw · English": "ctrl+alt+r"}, "Polish · English")
    assert verdict.level == "clash" and verdict.other == "Raw · English"


def test_the_reader_key_counts_too():
    assert check("f4", ASSIGNED, "Polish · English").level == "clash"


def test_a_key_does_not_clash_with_itself():
    assert check("f5", ASSIGNED, "Raw · English").level != "clash"


@pytest.mark.parametrize("key", ["f5", "f7"])
def test_browser_and_office_keys_warn_but_are_allowed(key):
    verdict = check(key, {}, "Polish · English")
    assert verdict.level == "warn"
    assert verdict.reason


def test_an_ordinary_key_is_fine():
    verdict = check("ctrl+alt+r", ASSIGNED, "Polish · English")
    assert verdict.level == "ok" and verdict.reason == ""


def test_the_window_says_it_cannot_see_other_apps_keys():
    assert "other" in CANNOT_SEE_OTHER_APPS.lower()


# ------------------------------------------------------------------ the capture box
@pytest.fixture
def box(qtbot):
    edit = HotkeyEdit("Polish · English", ASSIGNED, current="f6")
    qtbot.addWidget(edit)
    return edit


def test_pressing_keys_captures_them_as_the_keyboard_library_names_them(qtbot, box):
    with qtbot.waitSignal(box.captured, timeout=500) as seen:
        qtbot.keyClick(box, Qt.Key_F9, Qt.ShiftModifier | Qt.ControlModifier)
    assert box.key == "ctrl+shift+f9"
    assert seen.args == ["ctrl+shift+f9"]


def test_esc_is_refused_not_taken(qtbot, box):
    qtbot.keyClick(box, Qt.Key_Escape)
    assert box.key == "f6"                       # unchanged
    assert box.verdict.level == "refused"


def test_a_windows_key_combination_is_refused(qtbot, box):
    qtbot.keyClick(box, Qt.Key_R, Qt.MetaModifier)
    assert box.key == "f6" and box.verdict.level == "refused"


def test_a_clash_is_reported_and_not_accepted(qtbot, box):
    qtbot.keyClick(box, Qt.Key_F3, Qt.ShiftModifier)
    assert box.key == "f6"
    assert box.verdict.level == "clash"
    assert "Fix line" in box.message_text()


def test_a_warning_still_accepts_the_key(qtbot, box):
    qtbot.keyClick(box, Qt.Key_F7)
    assert box.key == "f7" and box.verdict.level == "warn"
    assert box.message_text()


def test_a_modifier_alone_waits_for_the_real_key(qtbot, box):
    qtbot.keyPress(box, Qt.Key_Shift)
    assert box.key == "f6"
