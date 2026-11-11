"""The history viewer (zeroflow/data_windows.py HistoryWindow) and what it changes in the
Dictation history file (zeroflow/history.py). Offscreen, logic not pixels."""
import os

import pytest

from zeroflow import history, i18n
from zeroflow.data_windows import HistoryWindow

THREE = ("[09:00:01] [EN_RAW]\nfirst dictation about apples\n\n"
         "[09:05:00] [AR_POLISH]\nمرحبا هذه الثانية\n\n"
         "[10:15:30] [EN_POLISH]\nthird one, about the quarterly report\n\n")


@pytest.fixture
def path(tmp_path):
    file = tmp_path / "history.md"
    file.write_text(THREE, encoding="utf-8")
    return str(file)


def viewer(qtbot, path, keep=True, confirm=True, **kw):
    i18n.choose("en")
    copied = []
    win = HistoryWindow(path, keep_history=keep, copy=copied.append,
                        confirm=lambda _question: confirm, **kw)
    qtbot.addWidget(win)
    win.copied = copied
    return win


def read(path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


# ------------------------------------------------------------------- reading the file
def test_entries_are_read_newest_first(path):
    entries = history.read_entries(path)
    assert [e.text for e in entries] == ["third one, about the quarterly report",
                                         "مرحبا هذه الثانية", "first dictation about apples"]
    assert (entries[0].time, entries[0].mode) == ("10:15:30", "EN_POLISH")


def test_the_trim_notice_is_not_an_entry(tmp_path):
    file = tmp_path / "history.md"
    file.write_text("[... older history trimmed on 2026-11-11 10:00 ...]\n\n" + THREE, encoding="utf-8")
    assert len(history.read_entries(str(file))) == 3


def test_a_missing_file_is_an_empty_history(tmp_path):
    assert history.read_entries(str(tmp_path / "none.md")) == []


def test_a_multi_line_dictation_is_one_entry(tmp_path):
    file = tmp_path / "history.md"
    file.write_text("[09:00:01] [EN_RAW]\nline one\nline two\n\n", encoding="utf-8")
    assert [e.text for e in history.read_entries(str(file))] == ["line one\nline two"]


# ---------------------------------------------------------------------------- the viewer
def test_the_viewer_shows_newest_first(qtbot, path):
    win = viewer(qtbot, path)
    assert win.shown_texts() == ["third one, about the quarterly report",
                                 "مرحبا هذه الثانية", "first dictation about apples"]


def test_search_finds_an_entry_ignoring_case(qtbot, path):
    win = viewer(qtbot, path)
    win.search_edit.setText("QUARTERLY")
    assert win.shown_texts() == ["third one, about the quarterly report"]
    win.search_edit.setText("مرحبا")
    assert win.shown_texts() == ["مرحبا هذه الثانية"]
    win.search_edit.setText("")
    assert len(win.shown_texts()) == 3


def test_copy_puts_the_selected_entry_on_the_clipboard(qtbot, path):
    win = viewer(qtbot, path)
    win.search_edit.setText("apples")
    win.list.setCurrentRow(0)
    win.copy_button.click()
    assert win.copied == ["first dictation about apples"]


def test_copy_keeps_the_entry_out_of_clipboard_history(qtbot, path):
    """By default Copy goes through win_clipboard.set_text, which marks it private."""
    from unittest import mock
    i18n.choose("en")
    with mock.patch("zeroflow.win_clipboard.set_text") as set_text:
        win = HistoryWindow(path, keep_history=True)
        qtbot.addWidget(win)
        win.list.setCurrentRow(0)
        win.copy_button.click()
    set_text.assert_called_once_with("third one, about the quarterly report")


def test_every_new_word_has_an_arabic_translation():
    prefixes = ("hist.", "vocab.", "diag.", "tray.history", "tray.vocabulary", "tray.diagnostics")
    missing = [key for key in i18n.EN if key.startswith(prefixes) and key not in i18n.AR]
    assert missing == []


def test_copy_with_nothing_selected_copies_nothing(qtbot, path):
    win = viewer(qtbot, path)
    win.list.setCurrentRow(-1)
    win.copy_button.click()
    assert win.copied == []


def test_delete_one_removes_only_that_entry_and_is_saved(qtbot, path):
    win = viewer(qtbot, path)
    win.list.setCurrentRow(1)                        # the Arabic one
    win.delete_button.click()
    assert "مرحبا" not in read(path)
    assert "apples" in read(path) and "quarterly" in read(path)
    assert win.shown_texts() == ["third one, about the quarterly report",
                                 "first dictation about apples"]


def test_delete_from_a_search_removes_the_entry_found(qtbot, path):
    win = viewer(qtbot, path)
    win.search_edit.setText("apples")
    win.list.setCurrentRow(0)
    win.delete_button.click()
    assert "apples" not in read(path)
    assert len(history.read_entries(path)) == 2


def test_delete_keeps_a_dictation_written_while_the_viewer_was_open(qtbot, path):
    """The Engine appends while the window is open; deleting an old entry must not
    rewrite the file from the window's stale copy and lose the new one."""
    win = viewer(qtbot, path)
    with open(path, "a", encoding="utf-8") as f:
        f.write("[11:00:00] [EN_RAW]\nwritten after the window opened\n\n")
    win.list.setCurrentRow(2)                        # "apples", as the window shows it
    win.delete_button.click()
    assert "written after the window opened" in read(path)
    assert "apples" not in read(path)


def test_clear_all_empties_the_file_after_asking(qtbot, path):
    win = viewer(qtbot, path)
    win.clear_button.click()
    assert history.read_entries(path) == []
    assert win.shown_texts() == []


def test_clear_all_declined_changes_nothing(qtbot, path):
    win = viewer(qtbot, path, confirm=False)
    win.clear_button.click()
    assert read(path) == THREE
    assert len(win.shown_texts()) == 3


def test_clear_all_leaves_the_debug_log_alone(qtbot, path, tmp_path):
    """Shift+F2 clears the history and the log; the viewer's Clear all is the history only."""
    log = tmp_path / "flow_debug.log"
    log.write_text("2026-11-11 10:00:00,000 - INFO - kept\n", encoding="utf-8")
    win = viewer(qtbot, path)
    win.clear_button.click()
    assert history.read_entries(path) == []
    assert log.read_text(encoding="utf-8") == "2026-11-11 10:00:00,000 - INFO - kept\n"


# ------------------------------------------------------------- Keep dictation history off
def test_with_history_off_the_viewer_says_so(qtbot, path):
    win = viewer(qtbot, path, keep=False)
    assert win.notice.isVisibleTo(win)
    assert "Keep dictation history" in win.notice.text()
    assert len(win.shown_texts()) == 3               # what was kept before is still shown
    on = viewer(qtbot, path, keep=True)
    assert not on.notice.isVisibleTo(on)


def test_with_history_off_opening_the_viewer_writes_nothing(qtbot, tmp_path):
    missing = tmp_path / "history.md"
    viewer(qtbot, str(missing), keep=False)
    assert not missing.exists()


def test_with_history_off_a_dictation_writes_nothing(tmp_path, monkeypatch):
    file = tmp_path / "history.md"
    monkeypatch.setattr(history, "HISTORY_FILE", str(file))
    monkeypatch.setattr(history.settings, "KEEP_HISTORY", False)
    history.log_to_history("never saved", "en_raw")
    assert not file.exists()


# --------------------------------------------------------------------- keys and language
def test_the_program_lets_go_of_its_keys_while_the_viewer_is_open(qtbot, path):
    calls = []
    win = viewer(qtbot, path, keys_pause=lambda: calls.append("pause"),
                 keys_resume=lambda: calls.append("resume"))
    win.show()
    win.show()
    assert calls == ["pause"]
    win.reject()
    assert calls == ["pause", "resume"]


def test_arabic_is_right_to_left(qtbot, path):
    from PySide6.QtCore import Qt
    i18n.choose("ar")
    try:
        win = HistoryWindow(path, keep_history=True, copy=lambda _t: None)
        qtbot.addWidget(win)
        assert win.layoutDirection() == Qt.RightToLeft
        assert win.windowTitle() == i18n.AR["hist.title"]
    finally:
        i18n.choose("en")
