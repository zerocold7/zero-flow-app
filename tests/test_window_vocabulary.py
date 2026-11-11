"""The vocabulary editor (zeroflow/data_windows.py VocabularyWindow) and the Learned
vocabulary file it changes (zeroflow/vocabulary.py). Offscreen, logic not pixels."""
from unittest import mock

import pytest

from zeroflow import i18n, vocabulary
from zeroflow.data_windows import VocabularyWindow


@pytest.fixture
def path(tmp_path):
    file = tmp_path / "vocabulary.txt"
    file.write_text("ChromaDB\nKokoro\nZero- Flow\n", encoding="utf-8")
    return str(file)


def editor(qtbot, path, tidy=lambda: None, **kw):
    i18n.choose("en")
    win = VocabularyWindow(path, tidy=tidy, **kw)
    qtbot.addWidget(win)
    return win


def words(path) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def test_the_editor_shows_the_learned_words(qtbot, path):
    assert editor(qtbot, path).shown_words() == ["ChromaDB", "Kokoro", "Zero- Flow"]


def test_add_is_saved(qtbot, path):
    win = editor(qtbot, path)
    win.word_edit.setText("  Qwen  ")
    win.add_button.click()
    assert words(path) == ["ChromaDB", "Kokoro", "Zero- Flow", "Qwen"]
    assert "Qwen" in win.shown_words()
    assert win.word_edit.text() == ""


def test_an_added_word_reaches_dictation_without_a_restart(qtbot, path, monkeypatch):
    monkeypatch.setattr(vocabulary, "VOCAB_CACHE_FILE", path)
    win = editor(qtbot, path)
    win.word_edit.setText("Qwen")
    win.add_button.click()
    assert "Qwen" in vocabulary.load_vocabulary()


def test_a_blank_or_repeated_word_is_refused(qtbot, path):
    win = editor(qtbot, path)
    for text in ("", "   ", "kokoro"):
        win.word_edit.setText(text)
        win.add_button.click()
    assert words(path) == ["ChromaDB", "Kokoro", "Zero- Flow"]
    assert win.status.text()


def test_a_sentence_is_refused(qtbot, path):
    win = editor(qtbot, path)
    win.word_edit.setText("this is far too long to be a term")
    win.add_button.click()
    assert words(path) == ["ChromaDB", "Kokoro", "Zero- Flow"]


def test_edit_is_saved(qtbot, path):
    win = editor(qtbot, path)
    win.list.setCurrentRow(1)
    assert win.word_edit.text() == "Kokoro"          # selecting a word puts it in the box
    win.word_edit.setText("Kokoro TTS")
    win.change_button.click()
    assert words(path) == ["ChromaDB", "Kokoro TTS", "Zero- Flow"]


def test_delete_is_saved(qtbot, path):
    win = editor(qtbot, path)
    win.list.setCurrentRow(0)
    win.delete_button.click()
    assert words(path) == ["Kokoro", "Zero- Flow"]
    assert win.shown_words() == ["Kokoro", "Zero- Flow"]


def test_a_word_learned_while_the_editor_is_open_is_kept(qtbot, path):
    """A Polish may learn a word while the window is open; a later edit must not drop it."""
    win = editor(qtbot, path)
    with vocabulary.VOCAB_LOCK:
        with mock.patch.object(vocabulary, "VOCAB_CACHE_FILE", path):
            vocabulary.append_vocabulary_word("Gemma")
    win.list.setCurrentRow(0)
    win.delete_button.click()
    assert words(path) == ["Kokoro", "Zero- Flow", "Gemma"]


def test_writes_hold_the_vocabulary_lock(qtbot, path):
    win = editor(qtbot, path)
    held = []
    real = vocabulary._write_words

    def spy(*args):
        held.append(vocabulary.VOCAB_LOCK._is_owned())
        return real(*args)

    with mock.patch.object(vocabulary, "_write_words", spy):
        win.word_edit.setText("Qwen")
        win.add_button.click()
    assert held == [True]


# ---------------------------------------------------------------------- Tidy vocabulary
def test_tidy_runs_on_a_worker_and_the_list_is_read_again(qtbot, path):
    import threading
    ran_on = []

    def tidy():
        ran_on.append(threading.current_thread() is threading.main_thread())
        with open(path, "w", encoding="utf-8") as f:
            f.write("ChromaDB\nKokoro\n")

    win = editor(qtbot, path, tidy=tidy)
    win.tidy_button.click()
    qtbot.waitUntil(lambda: win.shown_words() == ["ChromaDB", "Kokoro"], timeout=2000)
    assert ran_on == [False]
    assert win.tidy_button.isEnabled()


def test_tidy_is_the_existing_maintenance(qtbot, path):
    """With no tidy given, the button runs Shift+F1's own run_memory_maintenance."""
    i18n.choose("en")
    with mock.patch("zeroflow.engine.run_memory_maintenance") as maintenance:
        win = VocabularyWindow(path)
        qtbot.addWidget(win)
        win.tidy_button.click()
        qtbot.waitUntil(lambda: maintenance.called, timeout=2000)


def test_a_failing_tidy_says_so_and_frees_the_button(qtbot, path):
    def tidy():
        raise RuntimeError("AI down")

    win = editor(qtbot, path, tidy=tidy)
    win.tidy_button.click()
    qtbot.waitUntil(lambda: win.tidy_button.isEnabled(), timeout=2000)
    assert win.status.text()
    assert words(path) == ["ChromaDB", "Kokoro", "Zero- Flow"]


def test_the_program_lets_go_of_its_keys_while_the_editor_is_open(qtbot, path):
    calls = []
    win = editor(qtbot, path, keys_pause=lambda: calls.append("pause"),
                 keys_resume=lambda: calls.append("resume"))
    win.show()
    assert calls == ["pause"]
    win.reject()
    assert calls == ["pause", "resume"]
