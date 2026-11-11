"""The history viewer and the vocabulary editor: the two windows on what Zero- Flow keeps.

Both change the files the Engine writes while they are open, so every change is made to
the file as it is at that moment, under its lock (history.HISTORY_LOCK, VOCAB_LOCK),
never by writing back the window's own copy. Like the Settings window, both let go of
the program's keys while they are open, so typing in them runs nothing.

What they touch (the file, the clipboard, the question before Clear all, the Tidy run)
is handed in, so the tests run them with no real machine.
"""
import threading
from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)

from zeroflow import history, i18n, vocabulary
from zeroflow.i18n import tr


def _private_copy(text: str) -> None:
    """Copy with clipboard history left out, as every dictated text is."""
    from zeroflow import win_clipboard
    win_clipboard.set_text(text)


def run_tidy() -> None:
    """Tidy vocabulary: Shift+F1's own maintenance, unchanged."""
    from zeroflow import engine
    engine.run_memory_maintenance()


class KeysLetGoDialog(QDialog):
    """A window that lets go of the program's keys while it is open."""

    def __init__(self, keys_pause: Callable[[], None], keys_resume: Callable[[], None]):
        super().__init__()
        self._on_open, self._on_close, self._keys_let_go = keys_pause, keys_resume, False
        self.setLayoutDirection(Qt.RightToLeft if i18n.is_rtl() else Qt.LeftToRight)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._keys_let_go:
            self._keys_let_go = True
            self._on_open()

    def done(self, result) -> None:
        super().done(result)
        if self._keys_let_go:
            self._keys_let_go = False
            self._on_close()

    def _ask(self, question: str) -> bool:
        return QMessageBox.question(self, self.windowTitle(), question) == QMessageBox.Yes


# ---------------------------------------------------------------------- history viewer
class HistoryWindow(KeysLetGoDialog):
    def __init__(self, path: str, keep_history: bool,
                 copy: Callable[[str], None] = _private_copy,
                 confirm: Callable[[str], bool] | None = None,
                 keys_pause: Callable[[], None] = lambda: None,
                 keys_resume: Callable[[], None] = lambda: None):
        super().__init__(keys_pause, keys_resume)
        self.path, self._copy = path, copy
        self._confirm = confirm or self._ask
        self._entries: list[history.Entry] = []
        self._shown: list[history.Entry] = []
        self.setWindowTitle(tr("hist.title"))
        self.resize(560, 520)

        self.notice = QLabel(tr("hist.off"))
        self.notice.setWordWrap(True)
        self.notice.setVisible(not keep_history)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("hist.search"))
        self.search_edit.textChanged.connect(self._show)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.copy_button = QPushButton(tr("hist.copy"))
        self.delete_button = QPushButton(tr("hist.delete"))
        self.clear_button = QPushButton(tr("hist.clear"))
        self.status = QLabel()
        self.copy_button.clicked.connect(self.copy_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        self.clear_button.clicked.connect(self.clear_all)

        buttons = QHBoxLayout()
        for button in (self.copy_button, self.delete_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(self.clear_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.notice)
        layout.addWidget(self.search_edit)
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)
        layout.addWidget(self.status)
        self.reload()

    def reload(self) -> None:
        self._entries = history.read_entries(self.path)
        self._show()

    def _show(self) -> None:
        """The entries whose words hold the search, ignoring case, newest first."""
        wanted = self.search_edit.text().strip().casefold()
        self._shown = [e for e in self._entries if wanted in e.text.casefold()]
        self.list.clear()
        for entry in self._shown:
            item = QListWidgetItem(f"{entry.time}  ·  {entry.mode}\n{entry.text}")
            self.list.addItem(item)

    def shown_texts(self) -> list[str]:
        return [entry.text for entry in self._shown]

    def _selected(self) -> history.Entry | None:
        row = self.list.currentRow()
        return self._shown[row] if 0 <= row < len(self._shown) else None

    def copy_selected(self) -> None:
        entry = self._selected()
        if entry is not None:
            self._copy(entry.text)
            self.status.setText(tr("hist.copied"))

    def delete_selected(self) -> None:
        entry = self._selected()
        if entry is not None:
            history.delete_entry(entry, self.path)
            self.reload()

    def clear_all(self) -> None:
        if self._entries and self._confirm(tr("hist.clear_ask")):
            history.clear(self.path)
            self.reload()


# -------------------------------------------------------------------- vocabulary editor
class VocabularyWindow(KeysLetGoDialog):
    tidy_finished = Signal(str)          # "" when it ran, otherwise what went wrong

    def __init__(self, path: str, tidy: Callable[[], None] = run_tidy,
                 keys_pause: Callable[[], None] = lambda: None,
                 keys_resume: Callable[[], None] = lambda: None):
        super().__init__(keys_pause, keys_resume)
        self.path, self._tidy = path, tidy
        self.setWindowTitle(tr("vocab.title"))
        self.resize(420, 480)

        hint = QLabel(tr("vocab.hint"))
        hint.setWordWrap(True)
        self.list = QListWidget()
        self.list.currentTextChanged.connect(lambda text: self.word_edit.setText(text))
        self.word_edit = QLineEdit()
        self.add_button = QPushButton(tr("vocab.add"))
        self.change_button = QPushButton(tr("vocab.change"))
        self.delete_button = QPushButton(tr("vocab.delete"))
        self.tidy_button = QPushButton(tr("vocab.tidy"))
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.add_button.clicked.connect(self.add)
        self.change_button.clicked.connect(self.change)
        self.delete_button.clicked.connect(self.delete)
        self.tidy_button.clicked.connect(self.tidy)
        self.tidy_finished.connect(self._tidy_done)

        row = QHBoxLayout()
        row.addWidget(self.word_edit, 1)
        for button in (self.add_button, self.change_button, self.delete_button):
            row.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self.list, 1)
        layout.addLayout(row)
        layout.addWidget(self.tidy_button)
        layout.addWidget(self.status)
        self.reload()

    def reload(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        self.list.addItems(vocabulary.learned_words(self.path))
        self.list.blockSignals(False)

    def shown_words(self) -> list[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]

    def _selected(self) -> str | None:
        item = self.list.currentItem()
        return item.text() if item is not None and self.list.currentRow() >= 0 else None

    def _apply(self, change, word: str, ignore: str | None = None) -> None:
        """Check `word` against the file as it is now, then change it, all under the lock."""
        problem = []

        def checked(words):
            problem.append(vocabulary.word_problem(word, words, ignore))
            return words if problem[0] else change(words)

        vocabulary.change_learned_words(self.path, checked)
        self.status.setText(tr(f"vocab.{problem[0]}") if problem[0] else tr("vocab.saved"))
        if not problem[0]:
            self.word_edit.clear()
        self.reload()

    def add(self) -> None:
        word = self.word_edit.text().strip()
        self._apply(lambda words: [*words, word], word)

    def change(self) -> None:
        old, word = self._selected(), self.word_edit.text().strip()
        if old is not None:
            self._apply(lambda words: [word if w == old else w for w in words], word, ignore=old)

    def delete(self) -> None:
        old = self._selected()
        if old is not None:
            vocabulary.change_learned_words(self.path, lambda words: [w for w in words if w != old])
            self.word_edit.clear()
            self.status.setText(tr("vocab.saved"))
            self.reload()

    def tidy(self) -> None:
        """Runs on a worker: it asks the AI, which takes seconds."""
        self.tidy_button.setEnabled(False)
        self.status.setText(tr("vocab.tidy_running"))
        threading.Thread(target=self._run_tidy, daemon=True).start()

    def _run_tidy(self) -> None:
        try:
            self._tidy()
            self.tidy_finished.emit("")
        except Exception as e:
            self.tidy_finished.emit(f"{type(e).__name__}: {e}")

    def _tidy_done(self, problem: str) -> None:
        self.reload()
        self.tidy_button.setEnabled(True)
        self.status.setText(tr("vocab.tidy_failed") + problem if problem else tr("vocab.tidy_done"))
