"""Copy diagnostics (zeroflow/diagnostics.py): the version, detect(), the settings without
secrets and the last Debug log lines, and never a key, dictated words or the history.

The privacy tests plant a key and dictated words everywhere they could leak from (the
settings, Credential Manager, the history, the log in every form it can hold them) and
require that none of it is in the text."""
from unittest import mock

import pytest

import zeroflow
from zeroflow import credentials, diagnostics, logs, settings, storage

KEY = "sk-ant-PLANTED-KEY-0123456789abcdef"
WORDS = "purple elephant tango at midnight"          # a planted dictation
FACTS = {"windows": True, "os": "Windows 11", "python": "3.12.7", "cpu": "Test CPU",
         "threads": 16, "ram_gb": 32.0,
         "gpus": [{"name": "NVIDIA GeForce RTX 4070", "vram_gb": 12.0,
                   "vendor": "nvidia", "dedicated": True}]}


def log_line(message: str, level: str = "INFO") -> str:
    return f"2026-11-11 10:00:00,000 - {level} - {message}\n"


@pytest.fixture
def home(tmp_path):
    """A data folder and a logs folder holding the planted key and words."""
    data, logs_dir = tmp_path / "data", tmp_path / "logs"
    data.mkdir(), logs_dir.mkdir()
    values, _ = settings.resolve({})
    values.update(AI_PROVIDER="custom", AI_URL=f"https://user:{KEY}@api.example.com/v1?key={KEY}",
                  AI_MODEL="some-model")
    values.pop("AI_API_KEY", None)
    storage.save(str(data / "settings.json"), values)
    (data / "history.md").write_text(f"[09:00:01] [EN_RAW]\n{WORDS}\n\n"
                                     "[09:01:00] [EN_POLISH]\nsecond private note here\n\n",
                                     encoding="utf-8")
    (data / "vocabulary.txt").write_text("ChromaDB\nKokoro\n", encoding="utf-8")
    store = credentials.MemoryStore()
    store.set(credentials.provider_address("custom", values["AI_URL"]), KEY)

    with mock.patch.object(logs, "LOG_DICTATION_TEXT", True):
        shown = logs.said(WORDS)                      # "Show dictated words in the log" on
    (logs_dir / "flow_debug.log.1").write_text(
        "".join(log_line(f"older line {i}") for i in range(300)), encoding="utf-8")
    (logs_dir / "flow_debug.log").write_text(
        log_line("Engine is up (active).")
        + log_line(f"Transcribed: {shown}")
        + log_line(f"Polish answer was {WORDS}")              # a log call outside said()
        + log_line("a second private note here, logged raw")  # part of a history entry
        + log_line(f"Request failed: 401 for key {KEY}", "ERROR")
        + log_line(f"Authorization: Bearer {KEY}")
        + "".join(log_line(f"recent line {i}") for i in range(50)),
        encoding="utf-8")
    (logs_dir / "reader_debug.log").write_text(log_line("Reader ready."), encoding="utf-8")
    return {"settings": str(data / "settings.json"), "history": str(data / "history.md"),
            "vocabulary": str(data / "vocabulary.txt"), "logs": str(logs_dir), "store": store}


def report(home) -> str:
    return diagnostics.collect(home["store"], settings_path=home["settings"],
                               history_path=home["history"], vocabulary_path=home["vocabulary"],
                               log_dir=home["logs"], detect=lambda: FACTS)


# -------------------------------------------------------------------------- what it holds
def test_it_holds_the_version(home):
    assert zeroflow.__version__ in report(home)


def test_it_holds_what_detect_found(home):
    text = report(home)
    for shown in ("Test CPU", "NVIDIA GeForce RTX 4070", "32.0", "Windows 11", "3.12.7"):
        assert shown in text


def test_the_real_detect_is_used_by_default(home):
    with mock.patch("check_hardware.detect", return_value=FACTS) as detect:
        diagnostics.collect(home["store"], settings_path=home["settings"],
                            history_path=home["history"], vocabulary_path=home["vocabulary"],
                            log_dir=home["logs"])
    detect.assert_called_once()


def test_it_holds_the_settings(home):
    text = report(home)
    assert '"AI_PROVIDER": "custom"' in text
    assert '"AI_MODEL": "some-model"' in text
    assert '"HOTKEY_EN_RAW"' in text


def test_it_says_whether_a_key_is_saved_without_showing_it(home):
    assert "API key saved: yes" in report(home)


def test_it_holds_the_last_200_log_lines_reaching_into_the_backup(home):
    text = report(home)
    lines = diagnostics.log_section(text, "flow_debug.log")
    assert len(lines) == diagnostics.LOG_TAIL == 200
    assert lines[-1].endswith("recent line 49")
    assert any(line.endswith("older line 299") for line in lines)    # from the .1 backup
    assert not any(line.endswith("older line 0") for line in lines)


def test_it_holds_the_readers_log_too(home):
    assert "Reader ready." in report(home)


def test_it_counts_history_and_vocabulary_without_showing_them(home):
    text = report(home)
    assert "History entries: 2" in text
    assert "Learned words: 2" in text
    assert "ChromaDB" not in text


def test_missing_files_do_not_stop_it(tmp_path):
    text = diagnostics.collect(credentials.MemoryStore(),
                               settings_path=str(tmp_path / "none.json"),
                               history_path=str(tmp_path / "none.md"),
                               vocabulary_path=str(tmp_path / "none.txt"),
                               log_dir=str(tmp_path / "no-logs"), detect=lambda: FACTS)
    assert zeroflow.__version__ in text


def test_a_failing_detect_is_reported_not_raised(home):
    def broken():
        raise OSError("no registry")
    text = diagnostics.collect(home["store"], settings_path=home["settings"],
                               history_path=home["history"], vocabulary_path=home["vocabulary"],
                               log_dir=home["logs"], detect=broken)
    assert "no registry" in text


# ---------------------------------------------------------------- what it never holds
def test_the_planted_key_is_never_in_it(home):
    assert "PLANTED-KEY" not in report(home)


def test_the_planted_dictated_words_are_never_in_it(home):
    text = report(home)
    assert "purple elephant" not in text
    assert "second private note" not in text


def test_a_line_with_dictated_words_is_replaced_not_silently_dropped(home):
    """You can see that something was left out, and how many lines."""
    assert "left out" in report(home)


def test_the_settings_file_never_holds_a_key_even_when_planted(home, tmp_path):
    """An older file with AI_API_KEY in it (written by hand, say) still does not leak,
    even a key of no known shape that is not the saved one."""
    import json
    path = tmp_path / "planted.json"
    path.write_text(json.dumps({"AI_API_KEY": "plain-planted-0001", "AI_PROVIDER": "custom"}),
                    encoding="utf-8")
    text = diagnostics.collect(credentials.MemoryStore(), settings_path=str(path),
                               history_path=home["history"], vocabulary_path=home["vocabulary"],
                               log_dir=home["logs"], detect=lambda: FACTS)
    assert "plain-planted-0001" not in text


def test_the_saved_key_is_hidden_whatever_its_shape(home):
    """Each rule on its own: a saved key with no known shape, written plainly in the log."""
    import json
    plain = "PLAINSECRETzz9-planted"
    values = json.loads(open(home["settings"], encoding="utf-8").read())
    home["store"].set(credentials.provider_address("custom", values["AI_URL"]), plain)
    with open(f"{home['logs']}/flow_debug.log", "a", encoding="utf-8") as f:
        f.write(log_line(f"the server said no to {plain}"))
    assert "PLAINSECRET" not in report(home)


def test_marked_words_are_left_out_even_when_not_in_the_history(home):
    """Each rule on its own: with history off, the mark alone keeps the words out."""
    with mock.patch.object(logs, "LOG_DICTATION_TEXT", True):
        shown = logs.said("never kept anywhere else xyzzy")
    with open(f"{home['logs']}/flow_debug.log", "a", encoding="utf-8") as f:
        f.write(log_line(f"Transcribed: {shown}"))
    open(home["history"], "w").close()
    assert "xyzzy" not in report(home)


def test_a_secret_in_an_address_is_hidden_but_the_server_is_shown(home):
    text = report(home)
    assert "api.example.com" in text
    assert "user:" not in text and "?key=" not in text


def test_well_known_key_shapes_are_hidden_even_when_not_saved(home, tmp_path):
    """A key that is not the saved one (an old one, a different provider's) is still
    recognised by its shape."""
    other = "sk-proj-ANOTHERKEY0123456789abcdefghij"
    with open(f"{home['logs']}/flow_debug.log", "a", encoding="utf-8") as f:
        f.write(log_line(f"old key {other}"))
        f.write(log_line("api_key=hf_ABCDEFGHIJKLMNOPQRSTUVWXYZabcd"))
    text = report(home)
    assert "ANOTHERKEY" not in text
    assert "hf_ABCDEFGHIJ" not in text


def test_copy_puts_it_on_the_clipboard(home):
    copied = []
    diagnostics.copy(home["store"], copy=copied.append, settings_path=home["settings"],
                     history_path=home["history"], vocabulary_path=home["vocabulary"],
                     log_dir=home["logs"], detect=lambda: FACTS)
    assert len(copied) == 1 and zeroflow.__version__ in copied[0]
    assert "PLANTED-KEY" not in copied[0] and "purple elephant" not in copied[0]


def test_dictated_words_in_the_log_carry_a_mark_the_diagnostics_can_find():
    with mock.patch.object(logs, "LOG_DICTATION_TEXT", True):
        assert logs.said("hello").startswith(logs.DICTATED_MARK)
    with mock.patch.object(logs, "LOG_DICTATION_TEXT", False):
        assert logs.said("hello") == "(5 chars)"
