"""The first-run wizard: Interface language, this PC and what it should run, the models
folder, the AI Provider, the downloads, a microphone test and an AI test. Its logic is
zeroflow/first_run.py; this is only the window.

It runs only on a first start with nothing to migrate (first_run.needs_setup), and again
from "Run setup again" in the Settings window. Nothing is written until Finish: then the
API key goes to Credential Manager first, and the settings file is written in one step,
so a wizard closed half-way runs again on the next start. Like the Settings window, it
asks the Engine to let go of every key while it is open.

What it touches (the key store, the downloads, the microphone, the AI) is handed in, so
tests run it with no network, microphone or Credential Manager.
"""
import os
import shutil
import threading
import time
from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget,
                               QWizard, QWizardPage)

from zeroflow import credentials, first_run, i18n, settings, storage
from zeroflow.i18n import tr
from zeroflow.provider_form import ProviderPage
from zeroflow.settings_window import KEYS, WHISPER_MODELS

# The settings the wizard asks about. Run again, it changes only these.
ASKED = ("INTERFACE_LANGUAGE", "MODELS_DIR", "WHISPER_MODEL_NAME", "AI_PROVIDER", "AI_URL",
         "AI_MODEL", "OLLAMA_MODEL_NAME", "MICROPHONE")


def shown_size(size: int) -> str:
    if not size:
        return "?"
    return f"{size / 1e9:.1f} GB" if size >= 1e9 else f"{size / 1e6:.0f} MB"


class Page(QWizardPage):
    """A page whose Next button follows `complete()`."""

    def __init__(self, complete: Callable[[], bool] = lambda: True, entered=None):
        super().__init__()
        self._complete, self._entered = complete, entered

    def isComplete(self) -> bool:
        return self._complete()

    def initializePage(self) -> None:
        if self._entered:
            self._entered()


class Downloads(QObject):
    """Fetches the items one after another on a worker thread; Qt signals carry the news."""
    # item name, bytes so far, whole size (Python ints: a model is over Qt's 2 GB int)
    progress = Signal(str, object, object)
    changed = Signal(str, str)                # item name, state

    def __init__(self, items_now: Callable[[], tuple[list, str]], fetch, cached):
        super().__init__()
        self.items_now, self.fetch, self.cached = items_now, fetch, cached
        self.items: list = []
        self._states: dict[str, str] = {}
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()

    def states(self) -> dict[str, str]:
        return dict(self._states)

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def finished(self) -> bool:
        """Every item is in the folder."""
        return (not self.running() and bool(self._states)
                and all(state == "done" for state in self._states.values()))

    def start(self) -> None:
        if self.running():
            return
        self.items, cache_dir = self.items_now()
        self._states = {item.name: "waiting" for item in self.items}
        self._cancel = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(list(self.items), cache_dir,
                                                                self._cancel), daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def _set(self, name: str, state: str) -> None:
        self._states[name] = state
        self.changed.emit(name, state)

    def _run(self, items, cache_dir, cancel) -> None:
        for item in items:
            if cancel.is_set():
                self._set(item.name, "cancelled")
                continue
            try:
                here = self.cached(item, cache_dir)
            except Exception:
                here = False
            if here:
                self.progress.emit(item.name, item.size, item.size)
                self._set(item.name, "done")
                continue
            self._set(item.name, "downloading")
            state = first_run.run_download(
                item, cache_dir, self.fetch,
                lambda done, n=item.name, size=item.size: self.progress.emit(n, done, size),
                cancel)
            self._set(item.name, state)


class SetupWizard(QWizard):
    WELCOME, THIS_PC, MODELS, PROVIDER, DOWNLOADS, MIC, AI, DONE = range(8)
    completed = Signal()                       # the settings file is written: restart now
    _mic_done = Signal(object)
    _ai_done = Signal(object)

    def __init__(self, settings_path: str, store, microphones: list[str], startup=None, *,
                 detect=None, fetch=first_run.real_fetch, record=first_run.real_record,
                 ask_ai=first_run.real_ask, runtime_installed=None, cached=first_run.cached,
                 keys_pause: Callable[[], None] = lambda: None,
                 keys_resume: Callable[[], None] = lambda: None,
                 environ=None, ollama_models: list[str] | None = None):
        super().__init__()
        self.settings_path, self.store, self.startup = settings_path, store, startup
        self.record, self.ask_ai = record, ask_ai
        self._keys_pause, self._keys_resume, self._keys_paused = keys_pause, keys_resume, False
        self._runtime_installed = runtime_installed or self._runtime_is_installed
        self._texts: list[tuple[Callable[[str], None], str]] = []
        self.first_start = True

        defaults, _ = settings.resolve({})
        defaults.pop(storage.KEY_NAME, None)
        self.recommended = first_run.recommendation(detect=detect)
        self.default_models_dir = storage.default_models_dir(os.environ if environ is None
                                                             else environ)
        self.values = {**defaults, **self.recommended.values,
                       "MODELS_DIR": self.default_models_dir}

        self.setWizardStyle(QWizard.ModernStyle)
        self.setOption(QWizard.NoBackButtonOnStartPage)
        self.resize(640, 560)
        self.setPage(self.WELCOME, self._welcome_page())
        self.setPage(self.THIS_PC, self._this_pc_page())
        self.setPage(self.MODELS, self._models_page())
        self.setPage(self.PROVIDER, self._provider_page(ollama_models or []))
        self.downloads = Downloads(self._items_now, fetch, cached)
        self.setPage(self.DOWNLOADS, self._downloads_page())
        self.setPage(self.MIC, self._mic_page(microphones))
        self.setPage(self.AI, self._ai_page())
        self.setPage(self.DONE, self._done_page())
        self.setStartId(self.WELCOME)
        self._mic_done.connect(self._show_mic)
        self._ai_done.connect(self._show_ai)
        self._retranslate()
        self.restart()                            # on the first page, before it is shown

    # ------------------------------------------------------------------ texts and language
    def _t(self, setter: Callable[[str], None], key: str) -> None:
        """Show tr(key) now, and again whenever the Interface language changes."""
        self._texts.append((setter, key))

    def _label(self, key: str) -> QLabel:
        label = QLabel()
        label.setWordWrap(True)
        self._t(label.setText, key)
        return label

    def _retranslate(self) -> None:
        self.setLayoutDirection(Qt.RightToLeft if i18n.is_rtl() else Qt.LeftToRight)
        self.setWindowTitle(tr("wiz.title"))
        for button, key in ((QWizard.NextButton, "wiz.next"), (QWizard.BackButton, "wiz.back"),
                            (QWizard.FinishButton, "wiz.finish"),
                            (QWizard.CancelButton, "win.cancel")):
            self.setButtonText(button, tr(key))
        for setter, key in self._texts:
            setter(tr(key))
        if hasattr(self, "pc_label"):
            self.pc_label.setText(self.this_pc_text())

    def _language_chosen(self) -> None:
        i18n.choose(self.language_box.currentData())
        self._retranslate()

    # --------------------------------------------------------------------------- pages
    def _welcome_page(self) -> QWizardPage:
        page = Page()
        self._t(page.setTitle, "wiz.welcome")
        layout = QFormLayout(page)
        layout.addRow(self._label("wiz.welcome_text"))
        self.language_box = QComboBox()
        for key, code in (("lang.auto", "auto"), ("lang.en", "en"), ("lang.ar", "ar")):
            self.language_box.addItem(tr(key), code)
        self.language_box.setCurrentIndex(self.language_box.findData(
            self.values.get("INTERFACE_LANGUAGE", "auto")))
        self.language_box.currentIndexChanged.connect(self._language_chosen)
        name = QLabel()
        self._t(name.setText, "general.language")
        layout.addRow(name, self.language_box)
        return page

    def this_pc_text(self) -> str:
        r = self.recommended
        facts = r.facts
        cards = ", ".join(f"{g['name']} ({g['vram_gb']} GB)" for g in facts.get("gpus", [])
                          if g.get("dedicated")) or tr("wiz.no_card")
        lines = [f"{tr('wiz.cpu')}: {facts.get('cpu')}", f"{tr('wiz.ram')}: {facts.get('ram_gb')} GB",
                 f"{tr('wiz.card')}: {cards}", "", f"{tr('wiz.kind')}: {r.label}"]
        lines += [f"• {reason}" for reason in r.reasons]
        return "\n".join(lines)

    def _this_pc_page(self) -> QWizardPage:
        page = Page()
        self._t(page.setTitle, "wiz.this_pc")
        layout = QFormLayout(page)
        self.pc_label = QLabel(self.this_pc_text())
        self.pc_label.setWordWrap(True)
        self.pc_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addRow(self.pc_label)
        self.whisper_box = QComboBox()
        for model in WHISPER_MODELS:
            self.whisper_box.addItem(model, model)
        self._select(self.whisper_box, self.values["WHISPER_MODEL_NAME"])
        name = QLabel()
        self._t(name.setText, "speech.whisper")
        layout.addRow(name, self.whisper_box)
        layout.addRow(self._label("wiz.this_pc_hint"))
        return page

    @staticmethod
    def _select(box: QComboBox, value) -> None:
        if box.findData(value) < 0:
            box.addItem(str(value), value)
        box.setCurrentIndex(box.findData(value))

    def _models_page(self) -> QWizardPage:
        page = Page(complete=lambda: bool(self.models_dir_edit.text().strip()),
                    entered=self._show_space)
        self._t(page.setTitle, "adv.models")
        layout = QFormLayout(page)
        layout.addRow(self._label("wiz.models_text"))
        self.models_dir_edit = QLineEdit(self.values.get("MODELS_DIR") or self.default_models_dir)
        browse = QPushButton("…")
        browse.clicked.connect(lambda: self.models_dir_edit.setText(
            QFileDialog.getExistingDirectory(self, tr("adv.models"), self.models_dir_edit.text())
            or self.models_dir_edit.text()))
        row = QHBoxLayout()
        row.addWidget(self.models_dir_edit, 1)
        row.addWidget(browse)
        layout.addRow(row)
        self.space_label = QLabel()
        self.space_label.setWordWrap(True)
        layout.addRow(self.space_label)
        self.models_dir_edit.textChanged.connect(page.completeChanged)
        self.models_dir_edit.textChanged.connect(self._show_space)
        return page

    def _show_space(self) -> None:
        need = sum(item.size for item in self._items_now()[0])
        folder = self.models_dir_edit.text().strip()
        while folder and not os.path.exists(folder) and os.path.dirname(folder) != folder:
            folder = os.path.dirname(folder)
        try:
            free = shutil.disk_usage(folder).free if folder else 0
        except OSError:
            free = 0
        text = tr("wiz.space").format(need=shown_size(need), free=shown_size(free))
        if free and free < need:
            text += " " + tr("wiz.space_short")
        self.space_label.setText(text)

    def _provider_page(self, ollama_models: list[str]) -> QWizardPage:
        page = Page()
        self._t(page.setTitle, "tab.ai")
        layout = QVBoxLayout(page)
        layout.addWidget(self._label("wiz.ai_text"))
        self.provider_page = ProviderPage()
        for model in ollama_models:
            self.provider_page.ollama_model_box.addItem(model)
        self._show_provider()
        layout.addWidget(self.provider_page)
        return page

    def _show_provider(self) -> None:
        page = self.provider_page
        page.set_provider(self.values.get("AI_PROVIDER", "builtin"))
        page.url_edit.setText(self.values.get("AI_URL", ""))
        page.model_edit.setText(self.values.get("AI_MODEL", ""))
        page.ollama_model_box.setEditText(self.values.get("OLLAMA_MODEL_NAME", ""))
        address = credentials.provider_address(page.provider(), page.url_edit.text())
        try:
            saved = bool(address and self.store.get(address))
        except OSError:
            saved = False
        page.show_saved_key(saved)

    def _downloads_page(self) -> QWizardPage:
        page = Page(complete=self.downloads.finished, entered=self._enter_downloads)
        self._t(page.setTitle, "wiz.downloads")
        self.downloads_layout = QFormLayout(page)
        self.downloads_layout.addRow(self._label("wiz.downloads_text"))
        self.download_rows: dict[str, tuple[QLabel, QProgressBar]] = {}
        self.download_area = QWidget()
        self.downloads_layout.addRow(self.download_area)
        self.download_status = QLabel()
        self.download_status.setWordWrap(True)
        self.downloads_layout.addRow(self.download_status)
        buttons = QHBoxLayout()
        self.cancel_download_button = QPushButton()
        self._t(self.cancel_download_button.setText, "wiz.cancel_download")
        self.retry_button = QPushButton()
        self._t(self.retry_button.setText, "wiz.retry")
        self.cancel_download_button.clicked.connect(self.downloads.cancel)
        self.retry_button.clicked.connect(self._start_downloads)
        buttons.addWidget(self.cancel_download_button)
        buttons.addWidget(self.retry_button)
        self.downloads_layout.addRow(buttons)
        self._started_at: dict[str, tuple[float, int]] = {}
        self.downloads.progress.connect(self._show_progress)
        self.downloads.changed.connect(self._show_state)
        self.downloads.changed.connect(lambda *_: page.completeChanged.emit())
        return page

    def _enter_downloads(self) -> None:
        if not self.downloads.finished():
            self._start_downloads()

    def _start_downloads(self) -> None:
        self.downloads.start()
        rows = QFormLayout()
        old = self.download_area.layout()
        if old is not None:                      # a fresh list for this run
            QWidget().setLayout(old)
        self.download_rows.clear()
        for item in self.downloads.items:
            label, bar = QLabel(f"{item.label} — {shown_size(item.size)}"), QProgressBar()
            bar.setRange(0, 1000)
            rows.addRow(label, bar)
            self.download_rows[item.name] = (label, bar)
        self.download_area.setLayout(rows)
        self.download_status.setText("")

    def _show_progress(self, name: str, done: int, total: int) -> None:
        if name not in self.download_rows:
            return
        bar = self.download_rows[name][1]
        bar.setValue(int(1000 * done / total) if total else 0)
        start = self._started_at.setdefault(name, (time.monotonic(), done))
        seconds = time.monotonic() - start[0]
        if seconds > 2 and done > start[1] and total > done:
            speed = (done - start[1]) / seconds
            left = (total - done) / speed
            self.download_status.setText(tr("wiz.speed").format(
                speed=f"{speed * 8 / 1e6:.0f}", minutes=f"{left / 60:.0f}"))

    def _show_state(self, name: str, state: str) -> None:
        if name in self.download_rows and state == "done":
            self.download_rows[name][1].setValue(1000)
        if state.startswith("failed"):
            self.download_status.setText(tr("wiz.download_failed") + state[len("failed: "):])
        elif state == "cancelled":
            self.download_status.setText(tr("wiz.download_cancelled"))
        elif self.downloads.finished():
            self.download_status.setText(tr("wiz.downloads_done"))

    def _items_now(self) -> tuple[list, str]:
        values = self.collect()
        variant = values.get("LLAMA_VARIANT", "auto")
        if variant == "auto":
            from zeroflow.llm import llama_runtime
            variant = llama_runtime.pick_variant(
                [g["name"] for g in self.recommended.facts.get("gpus", [])])
        items = first_run.downloads_for(values, variant, self._runtime_installed(variant))
        return items, os.path.join(values["MODELS_DIR"], "hub")

    @staticmethod
    def _runtime_is_installed(variant: str) -> bool:
        from zeroflow.llm import llama_runtime
        return llama_runtime.installed(variant)

    def _mic_page(self, microphones: list[str]) -> QWizardPage:
        page = Page()
        self._t(page.setTitle, "general.mic")
        layout = QFormLayout(page)
        layout.addRow(self._label("wiz.mic_text"))
        self.mic_box = QComboBox()
        self.mic_box.addItem(tr("general.mic_default"), "")
        for name in microphones:
            self.mic_box.addItem(name, name)
        self._select(self.mic_box, self.values.get("MICROPHONE", ""))
        layout.addRow(self.mic_box)
        self.mic_button = QPushButton()
        self._t(self.mic_button.setText, "wiz.mic_test")
        self.mic_button.clicked.connect(lambda: self._in_background(self.mic_button,
                                                                    self.test_microphone))
        layout.addRow(self.mic_button)
        self.mic_result = QLabel()
        self.mic_result.setWordWrap(True)
        layout.addRow(self.mic_result)
        return page

    def _ai_page(self) -> QWizardPage:
        page = Page()
        self._t(page.setTitle, "wiz.ai_test_title")
        layout = QFormLayout(page)
        layout.addRow(self._label("wiz.ai_test_text"))
        self.ai_button = QPushButton()
        self._t(self.ai_button.setText, "wiz.ai_test")
        self.ai_button.clicked.connect(lambda: self._in_background(self.ai_button, self.test_ai))
        layout.addRow(self.ai_button)
        self.ai_result = QLabel()
        self.ai_result.setWordWrap(True)
        layout.addRow(self.ai_result)
        return page

    def _done_page(self) -> QWizardPage:
        page = Page()
        self._t(page.setTitle, "wiz.done")
        layout = QFormLayout(page)
        layout.addRow(self._label("wiz.done_text"))
        for name, label_key in KEYS[:6]:
            key, shown = QLabel(str(self.values.get(name, "")).upper()), QLabel()
            self._t(shown.setText, label_key)
            layout.addRow(shown, key)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addRow(self.status)
        return page

    # --------------------------------------------------------------------------- tests
    def _in_background(self, button: QPushButton, test) -> None:
        button.setEnabled(False)
        threading.Thread(target=test, daemon=True).start()

    def test_microphone(self) -> first_run.Result:
        result = first_run.mic_test(self.record, self.mic_box.currentData())
        self._mic_done.emit(result)
        return result

    @staticmethod
    def _verdict(result) -> str:
        return f"{tr('wiz.pass') if result.ok else tr('wiz.fail')}: {result.message}"

    def _show_mic(self, result) -> None:
        self.mic_result.setText(self._verdict(result))
        self.mic_button.setEnabled(True)

    def test_ai(self) -> first_run.Result:
        values = self.collect()
        key = self.provider_page.key_edit.text() or None
        result = first_run.ai_test(lambda text: self.ask_ai(values, key, text))
        self._ai_done.emit(result)
        return result

    def _show_ai(self, result) -> None:
        self.ai_result.setText(self._verdict(result))
        self.ai_button.setEnabled(True)

    # ------------------------------------------------------------------ run again, finish
    def load_current(self) -> None:
        """Run again from Settings: start from the settings in the file, not the
        recommendation, and change only what the wizard asks about."""
        self.first_start = False
        current, _ = settings.resolve(storage.load(self.settings_path))
        current.pop(storage.KEY_NAME, None)
        self.values = current
        self._select(self.language_box, current["INTERFACE_LANGUAGE"])
        self._select(self.whisper_box, current["WHISPER_MODEL_NAME"])
        self.models_dir_edit.setText(current["MODELS_DIR"])
        self._select(self.mic_box, current["MICROPHONE"])
        self._show_provider()

    def collect(self) -> dict:
        """Every setting, with the wizard's answers in. Never the API key."""
        page = self.provider_page
        values = dict(self.values)
        values.update({
            "INTERFACE_LANGUAGE": self.language_box.currentData(),
            "MODELS_DIR": self.models_dir_edit.text().strip(),
            "WHISPER_MODEL_NAME": self.whisper_box.currentData(),
            "AI_PROVIDER": page.provider(),
            "AI_URL": page.url_edit.text().strip() or self.values.get("AI_URL", ""),
            "AI_MODEL": page.model_edit.text().strip(),
            "OLLAMA_MODEL_NAME": page.ollama_model_box.currentText().strip(),
            "MICROPHONE": self.mic_box.currentData(),
        })
        values.pop(storage.KEY_NAME, None)
        return values

    def finish_setup(self) -> bool:
        """Store the key, then write the settings file. False, with the reason shown, when
        something stops it; then nothing is written."""
        page = self.provider_page
        if problems := page.problems():
            self._say(problems[0])
            return False
        values = self.collect()
        address = credentials.provider_address(values["AI_PROVIDER"], values["AI_URL"])
        key = page.key_edit.text()
        try:
            if address and key:
                self.store.set(address, key)
            elif address and page.clear_key_requested:
                self.store.delete(address)
        except OSError as e:
            self._say(tr("problem.key") + f"Windows Credential Manager (error {e.errno}).")
            return False
        if self.first_start or not os.path.exists(self.settings_path):
            written = values
        else:
            written = storage.load(self.settings_path)
            written.update({name: values[name] for name in ASKED})
        storage.save(self.settings_path, written)
        self.completed.emit()
        return True

    def _say(self, text: str) -> None:
        self.status.setText(text)

    def accept(self) -> None:
        if self.finish_setup():
            super().accept()

    # ------------------------------------------------------------ the keys while it is open
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._keys_paused:
            self._keys_pause()
            self._keys_paused = True

    def done(self, result) -> None:
        self.downloads.cancel()
        super().done(result)
        if self._keys_paused:
            self._keys_resume()
            self._keys_paused = False
