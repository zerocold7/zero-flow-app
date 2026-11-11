"""The Settings window (zeroflow/settings_window.py): what Save writes, what restarts the
Engine, the microphone picker, the languages. Offscreen, logic not pixels."""
import json

import pytest
from PySide6.QtCore import Qt

from zeroflow import credentials, i18n, microphone, settings, storage
from zeroflow.settings_window import (LIVE, SettingsWindow, changed_settings, restart_needed,
                                      startup_command)

SECRET = "sk-test-0123456789-SECRET"


class FakeStartup:
    def __init__(self):
        self.on = False

    def get(self):
        return self.on

    def set(self, on):
        self.on = on


def defaults() -> dict:
    values, _ = settings.resolve({})
    values["DICTATION_ON"] = values["READER_ON"] = True
    return values


@pytest.fixture
def window(qtbot, tmp_path):
    i18n.choose("en")
    path = tmp_path / "settings.json"
    values = defaults()
    storage.save(str(path), {k: v for k, v in values.items() if k != "AI_API_KEY"})
    live, store = [], credentials.MemoryStore()
    win = SettingsWindow(values, str(path), store, ["Desk mic", "Headset"], FakeStartup(),
                         lambda name, on: live.append((name, on)), ["qwen2.5:7b"])
    qtbot.addWidget(win)
    win.live, win.store, win.path = live, store, str(path)
    return win


def saved(win) -> dict:
    with open(win.path, encoding="utf-8") as f:
        return json.load(f)


def press(qtbot, box, key, modifier=Qt.NoModifier):
    qtbot.keyClick(box, key, modifier)


# ----------------------------------------------------------------- what changed, what restarts
def test_only_differences_count():
    assert changed_settings({"A": 1, "B": 2}, {"A": 1, "B": 3}) == {"B": 3}


def test_the_two_switches_do_not_restart_and_everything_else_does():
    assert LIVE == ("DICTATION_ON", "READER_ON")
    assert not restart_needed({"DICTATION_ON": False, "READER_ON": False})
    assert restart_needed({"HOTKEY_EN_RAW": "f11"})
    assert restart_needed({"DICTATION_ON": False, "MICROPHONE": "Desk mic"})


def test_a_window_with_nothing_changed_saves_nothing(qtbot, window):
    assert window.collect() == {}
    with qtbot.waitSignal(window.saved, timeout=500) as seen:
        window.save()
    assert seen.args == [False]                      # no restart for no change
    assert window.live == []


# ----------------------------------------------------------------------------- switches
def test_dictation_off_applies_at_once_with_no_restart_and_is_not_written_by_the_window(qtbot, window):
    window.dictation_box.setChecked(False)
    with qtbot.waitSignal(window.saved, timeout=500) as seen:
        window.save()
    assert seen.args == [False]
    assert window.live == [("DICTATION_ON", False)]
    assert "DICTATION_ON" not in saved(window) or saved(window)["DICTATION_ON"] is True


def test_the_window_says_paused_when_both_are_off(window):
    window.dictation_box.setChecked(False)
    assert not window.paused_label.isVisibleTo(window)
    window.reader_box.setChecked(False)
    assert window.paused_label.isVisibleTo(window)


# ------------------------------------------------------------------------------- hotkeys
def test_a_hotkey_changed_in_the_window_is_saved_and_restarts(qtbot, window):
    press(qtbot, window.key_boxes["HOTKEY_EN_RAW"], Qt.Key_F11)
    with qtbot.waitSignal(window.saved, timeout=500) as seen:
        window.save()
    assert seen.args == [True]
    assert saved(window)["HOTKEY_EN_RAW"] == "f11"


def test_a_clashing_hotkey_is_not_taken_and_names_the_other(qtbot, window):
    box = window.key_boxes["HOTKEY_EN_RAW"]
    press(qtbot, box, Qt.Key_F3, Qt.ShiftModifier)                  # Fix line's key
    assert box.key == "f5"
    assert "Fix line" in window.key_notes["HOTKEY_EN_RAW"].text()
    assert window.collect() == {}


def test_a_key_taken_in_the_window_counts_for_the_next_box(qtbot, window):
    press(qtbot, window.key_boxes["HOTKEY_EN_RAW"], Qt.Key_F11)
    box = window.key_boxes["HOTKEY_EN_POLISH"]
    press(qtbot, box, Qt.Key_F11)
    assert box.key == "f6" and box.verdict.level == "clash"


def test_the_window_says_it_cannot_see_other_apps(window):
    from zeroflow.hotkey_capture import CANNOT_SEE_OTHER_APPS
    labels = [w.text() for w in window.tabs.widget(1).findChildren(type(window.status))]
    assert CANNOT_SEE_OTHER_APPS in labels


# ------------------------------------------------------------------------------ microphone
def test_the_picker_lists_the_microphones_and_the_default_first(window):
    names = [window.mic_box.itemText(i) for i in range(window.mic_box.count())]
    assert names == ["Windows default", "Desk mic", "Headset"]


def test_picking_a_microphone_stores_its_name_and_the_default_stores_blank(qtbot, window):
    window.mic_box.setCurrentIndex(window.mic_box.findData("Headset"))
    assert window.collect() == {"MICROPHONE": "Headset"}
    with qtbot.waitSignal(window.saved, timeout=500) as seen:
        window.save()
    assert seen.args == [True] and saved(window)["MICROPHONE"] == "Headset"
    window.mic_box.setCurrentIndex(0)
    assert window.collect() == {"MICROPHONE": ""}


def test_a_saved_microphone_that_is_unplugged_is_kept_not_dropped(qtbot, tmp_path):
    values = defaults()
    values["MICROPHONE"] = "Old mic"
    path = tmp_path / "s.json"
    storage.save(str(path), {k: v for k, v in values.items() if k != "AI_API_KEY"})
    win = SettingsWindow(values, str(path), credentials.MemoryStore(), ["Desk mic"],
                         FakeStartup(), lambda *a: None)
    qtbot.addWidget(win)
    assert win.mic_box.currentData() == "Old mic"
    assert win.collect() == {}                       # saving does not forget it


# ------------------------------------------------------------------- the Reader's output
def reader_window(qtbot, tmp_path, speakers, **saved_values):
    values = defaults() | saved_values
    path = tmp_path / "s.json"
    storage.save(str(path), {k: v for k, v in values.items() if k != "AI_API_KEY"})
    win = SettingsWindow(values, str(path), credentials.MemoryStore(), [], FakeStartup(),
                         lambda *a: None, speakers=speakers)
    qtbot.addWidget(win)
    return win


def test_the_output_picker_lists_the_speakers_and_the_default_first(qtbot, tmp_path):
    win = reader_window(qtbot, tmp_path, ["Speakers", "Headphones"])
    names = [win.output_box.itemText(i) for i in range(win.output_box.count())]
    assert names == ["Windows default", "Speakers", "Headphones"]
    assert win.output_box.currentData() == ""


def test_picking_an_output_stores_its_name_and_restarts(qtbot, tmp_path):
    win = reader_window(qtbot, tmp_path, ["Speakers", "Headphones"])
    win.output_box.setCurrentIndex(win.output_box.findData("Headphones"))
    assert win.collect() == {"READER_OUTPUT": "Headphones"}
    assert restart_needed(win.collect())


def test_a_saved_output_that_is_unplugged_is_kept_not_dropped(qtbot, tmp_path):
    win = reader_window(qtbot, tmp_path, ["Speakers"], READER_OUTPUT="Old TV")
    assert win.output_box.currentData() == "Old TV"
    assert "not connected" in win.output_box.currentText()
    assert win.collect() == {}


def test_without_a_device_list_the_output_picker_still_offers_the_default(window):
    assert window.output_box.count() == 1 and window.output_box.currentData() == ""


def test_the_output_picker_is_named_in_both_languages():
    for language in ("en", "ar"):
        i18n.choose(language)
        assert i18n.tr("speech.output") != "speech.output"
    i18n.choose("en")


NAMES = [{"name": "Mic A", "max_input_channels": 1, "hostapi": 0},
         {"name": "Mic A", "max_input_channels": 1, "hostapi": 2},
         {"name": "Speakers", "max_input_channels": 0, "hostapi": 0}]


def test_microphone_names_are_listed_once_and_only_those_that_record():
    assert microphone.input_names(NAMES) == ["Mic A"]


def test_a_named_microphone_is_found_in_the_default_audio_system():
    assert microphone.resolve("Mic A", NAMES, default_host_api=2) == (1, False)
    assert microphone.resolve("Mic A", NAMES, default_host_api=0) == (0, False)


def test_a_missing_microphone_falls_back_to_the_default_and_says_so():
    assert microphone.resolve("Gone", NAMES) == (None, True)
    assert microphone.resolve("", NAMES) == (None, False)


# ---------------------------------------------------------------------------- AI provider
def test_choosing_custom_and_a_key_saves_both_the_right_way(qtbot, window):
    page = window.provider_page
    page.choose_preset("claude")
    page.key_edit.setText(SECRET)
    with qtbot.waitSignal(window.saved, timeout=500) as seen:
        window.save()
    assert seen.args == [True]
    assert saved(window)["AI_PROVIDER"] == "custom"
    assert window.store.get("https://api.anthropic.com") == SECRET
    with open(window.path, encoding="utf-8") as f:
        assert SECRET not in f.read()


def test_a_failed_key_save_changes_nothing_and_says_why(qtbot, window):
    class Broken(credentials.MemoryStore):
        def set(self, address, key):
            raise OSError(5, "no")
    window.store = Broken()
    page = window.provider_page
    page.choose_preset("claude")
    page.key_edit.setText(SECRET)
    before = saved(window)
    with qtbot.waitSignal(window.failed, timeout=500):
        window.save()
    assert saved(window) == before
    assert SECRET not in window.status.text()


def test_an_ollama_model_is_picked_from_the_list(qtbot, window):
    window.provider_page.set_provider("ollama")
    window.provider_page.ollama_model_box.setCurrentText("qwen2.5:7b")
    with qtbot.waitSignal(window.saved, timeout=500):
        window.save()
    assert saved(window)["AI_PROVIDER"] == "ollama"
    assert saved(window)["OLLAMA_MODEL_NAME"] == "qwen2.5:7b"


def test_plain_http_to_another_computer_with_a_key_is_refused_before_saving(qtbot, window):
    page = window.provider_page
    page.set_provider("custom")
    page.url_edit.setText("http://example.com/v1")
    page.key_edit.setText(SECRET)
    before = saved(window)
    window.save()
    assert saved(window) == before
    assert "http" in window.status.text()


# -------------------------------------------------------------------------------- the rest
def test_start_with_windows_is_the_registry_not_the_file(qtbot, window):
    window.startup_box.setChecked(True)
    with qtbot.waitSignal(window.saved, timeout=500):
        window.save()
    assert window.startup.on is True
    assert "START_WITH_WINDOWS" not in saved(window)


def test_the_start_up_command_runs_pythonw_with_the_entry_point(tmp_path):
    (tmp_path / "pythonw.exe").write_text("")
    command = startup_command(r"C:\app", str(tmp_path / "python.exe"))
    assert "pythonw.exe" in command and command.endswith('zero_flow.py"')


def test_new_settings_default_as_the_table_says():
    assert (settings.DICTATION_ON, settings.READER_ON) == (True, True)
    values = defaults()
    assert values["KEEP_HISTORY"] is True and values["READER_SPEED"] == 1.0
    assert values["MICROPHONE"] == "" and values["LANGUAGE_PAIR"] == "en-ar"
    assert values["INTERFACE_LANGUAGE"] == "auto"


def test_dictation_history_is_not_written_when_it_is_off(tmp_path, monkeypatch):
    from zeroflow import history
    target = tmp_path / "history.md"
    monkeypatch.setattr(history, "HISTORY_FILE", str(target))
    monkeypatch.setattr(history.settings, "KEEP_HISTORY", False)
    history.log_to_history("some words", "en_raw")
    assert not target.exists()
    monkeypatch.setattr(history.settings, "KEEP_HISTORY", True)
    history.log_to_history("some words", "en_raw")
    assert "some words" in target.read_text(encoding="utf-8")


# ------------------------------------------------------------------------------ languages
def test_arabic_has_a_table_and_switches_to_right_to_left(qtbot, tmp_path):
    i18n.choose("ar")
    try:
        assert i18n.is_rtl() and i18n.tr("win.save") != i18n.EN["win.save"]
        values = defaults()
        path = tmp_path / "s.json"
        storage.save(str(path), {k: v for k, v in values.items() if k != "AI_API_KEY"})
        win = SettingsWindow(values, str(path), credentials.MemoryStore(), [], FakeStartup(),
                             lambda *a: None)
        qtbot.addWidget(win)
        assert win.layoutDirection() == Qt.RightToLeft
    finally:
        i18n.choose("en")


def test_a_key_missing_from_a_table_shows_its_english_text():
    i18n.choose("ar")
    try:
        saved_text = i18n.AR.pop("win.save")
        assert i18n.tr("win.save") == i18n.EN["win.save"]
        i18n.AR["win.save"] = saved_text
    finally:
        i18n.choose("en")


def test_every_arabic_key_exists_in_english():
    assert set(i18n.AR) <= set(i18n.EN)
    assert set(i18n.EN) <= set(i18n.AR)               # and nothing is left untranslated


def test_windows_language_is_followed_when_it_is_auto(monkeypatch):
    monkeypatch.setattr(i18n, "windows_language", lambda: "ar")
    assert i18n.choose("auto") == "ar"
    i18n.choose("en")


def test_the_tray_lists_every_key_with_its_name():
    from zeroflow.app import shown_keys
    i18n.choose("en")
    rows = dict(shown_keys())
    assert len(rows) == 11
    assert rows["Raw · Arabic"] == settings.HOTKEYS["ar_raw"].upper()
    assert rows["Reader · Read the selection"] == settings.HOTKEY_READ.upper()
    assert rows["Cancel recording / silence the Reader"] == "ESC"


# ----------------------------------------------------- the keys are let go while it is open
def test_the_program_lets_go_of_its_keys_while_the_window_is_open(qtbot, tmp_path):
    """A key pressed to be captured must reach the window, not run what it is bound to
    (F5 started a recording instead of being taken)."""
    values = defaults()
    path = tmp_path / "s.json"
    storage.save(str(path), {k: v for k, v in values.items() if k != "AI_API_KEY"})
    calls = []
    win = SettingsWindow(values, str(path), credentials.MemoryStore(), [], FakeStartup(),
                         lambda *a: None, keys_pause=lambda: calls.append("pause"),
                         keys_resume=lambda: calls.append("resume"))
    qtbot.addWidget(win)
    assert calls == []
    win.show()
    win.show()                                       # shown again: still only once
    assert calls == ["pause"]
    win.reject()
    assert calls == ["pause", "resume"]
    win.show()                                       # opened a second time
    win.accept()                                     # and closed by Save
    assert calls == ["pause", "resume", "pause", "resume"]


def test_the_engine_lets_go_of_its_keys_and_takes_them_back_once():
    from unittest import mock

    from zeroflow import engine
    with mock.patch.object(engine.keyboard, "add_hotkey", side_effect=lambda *a, **k: object()), \
         mock.patch.object(engine.keyboard, "remove_hotkey") as remove, \
         mock.patch.object(engine, "on_cancel_hotkey"):
        engine._bound.clear()
        engine.register_hotkeys()
        held = len(engine._bound)
        assert held == 10
        engine.pause_hotkeys()
        assert engine._bound == [] and remove.call_count == held
        engine.resume_hotkeys()
        engine.resume_hotkeys()                      # resumed twice: bound once
        assert len(engine._bound) == held
        engine._bound.clear()


def test_the_reader_follows_the_pause_and_binds_its_keys_again():
    from unittest import mock

    from reader import app as reader_app
    states = iter([False, True, True, False])
    events = []
    with mock.patch.object(reader_app.keyboard, "add_hotkey",
                           side_effect=lambda *a, **k: events.append("bind") or object()), \
         mock.patch.object(reader_app.keyboard, "remove_hotkey",
                           side_effect=lambda h: events.append("unbind")), \
         mock.patch.object(reader_app.signals, "keys_paused", side_effect=lambda: next(states)), \
         mock.patch.object(reader_app.time, "sleep", side_effect=[None, None, None, StopIteration]):
        reader_app._bound.clear()
        reader_app.bind_keys()
        events.clear()
        try:
            reader_app.follow_keys_pause(poll=0)
        except StopIteration:
            pass
    assert events == ["unbind", "unbind", "bind", "bind"]       # two keys each way
    assert len(reader_app._bound) == 2
    reader_app._bound.clear()


def test_the_pause_is_shared_between_the_processes():
    from zeroflow import signals
    assert signals.keys_paused() is False
    signals.set_keys_paused(True)
    try:
        assert signals.keys_paused() is True
    finally:
        signals.set_keys_paused(False)
    assert signals.keys_paused() is False
