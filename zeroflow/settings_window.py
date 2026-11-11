"""The Settings window: every setting of docs/settings-table.md, in tabs.

Everything saves with one Save button. Dictation on and Reader on apply at once, with
no restart (through `apply_live`); anything else is written to the settings file and the
Engine restarts, which is how hotkeys, the microphone and the AI Provider take effect.
The API key never goes in the file: it goes to Credential Manager (key_saving).

The window is given what it touches (the key store, the file path, the list of
microphones, the Windows start-up switch) so tests can run it without a real machine.
"""
import os
from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from zeroflow import credentials, i18n, storage
from zeroflow.hotkey_capture import CANNOT_SEE_OTHER_APPS, HotkeyEdit
from zeroflow.i18n import tr
from zeroflow.key_saving import KeyNotSaved, save_provider
from zeroflow.provider_form import ProviderPage
from zeroflow.voices import VOICES

# Applied the moment they are saved, with no restart.
LIVE = ("DICTATION_ON", "READER_ON")
# Settings that are the AI Provider page's; written together with the key.
PROVIDER_SETTINGS = ("AI_PROVIDER", "AI_URL", "AI_MODEL", "OLLAMA_MODEL_NAME")

# The setting of each key, in the order shown, and its name in the translation table.
KEYS = [("HOTKEY_EN_RAW", "keys.raw_en"), ("HOTKEY_EN_POLISH", "keys.polish_en"),
        ("HOTKEY_AR_RAW", "keys.raw_ar"), ("HOTKEY_AR_POLISH", "keys.polish_ar"),
        ("HOTKEY_EN2AR", "keys.en2ar"), ("HOTKEY_AR2EN", "keys.ar2en"),
        ("HOTKEY_FIX", "keys.fix"), ("HOTKEY_MAINTENANCE", "keys.maintenance"),
        ("HOTKEY_PURGE", "keys.purge"), ("HOTKEY_READ", "keys.read")]
# The built-in AI's models: a fixed list, shown by name (repo, file).
BUILTIN_MODELS = {"Gemma 4 E4B (default)": ("google/gemma-4-E4B-it-qat-q4_0-gguf",
                                            "gemma-4-E4B_q4_0-it.gguf")}
WHISPER_MODELS = ("large-v3", "large-v3-turbo", "medium", "small", "base")
COMPUTE_TYPES = ("float16", "int8_float16", "int8", "float32")


def changed_settings(old: dict, new: dict) -> dict:
    """The settings in `new` whose value differs from `old`."""
    return {name: value for name, value in new.items() if old.get(name) != value}


def restart_needed(changed: dict) -> bool:
    """Whether the Engine must restart for these changes: anything but the live switches."""
    return any(name not in LIVE for name in changed)


class SettingsWindow(QDialog):
    saved = Signal(bool)              # True: the Engine must restart now
    failed = Signal(str)
    setup_requested = Signal()        # "Run setup again": the app opens the wizard

    def __init__(self, values: dict, settings_path: str, store, microphones: list[str],
                 startup, apply_live: Callable[[str, bool], None],
                 ollama_models: list[str] | None = None, key_saved: bool = False,
                 keys_pause: Callable[[], None] = lambda: None,
                 keys_resume: Callable[[], None] = lambda: None,
                 speakers: list[str] | None = None):
        super().__init__()
        self.values = dict(values)
        self._speakers = speakers or []           # the Reader's outputs, by name
        self.settings_path, self.store, self.startup = settings_path, store, startup
        self.apply_live = apply_live
        self._keys_pause, self._keys_resume, self._keys_paused = keys_pause, keys_resume, False
        self._get: dict[str, Callable] = {}
        self.assigned = {}
        self.setWindowTitle(tr("win.title"))
        self.setLayoutDirection(Qt.RightToLeft if i18n.is_rtl() else Qt.LeftToRight)
        self.resize(560, 560)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._general_tab(microphones), tr("tab.general"))
        self.tabs.addTab(self._keys_tab(), tr("tab.keys"))
        self.provider_page = self._provider_tab(ollama_models or [], key_saved)
        self.tabs.addTab(self.provider_page, tr("tab.ai"))
        self.tabs.addTab(self._speech_tab(), tr("tab.speech"))
        self.tabs.addTab(self._advanced_tab(), tr("tab.advanced"))

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.save_button = QPushButton(tr("win.save"))
        self.cancel_button = QPushButton(tr("win.cancel"))
        self.save_button.clicked.connect(self.save)
        self.cancel_button.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(self.status, 1)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.cancel_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addLayout(buttons)

    # ----------------------------------------------------------- the keys while it is open
    def showEvent(self, event) -> None:
        """Every key the program holds is let go while this window is open: pressing one
        to capture it must reach the window, not run what it is bound to."""
        super().showEvent(event)
        if not self._keys_paused:
            self._keys_paused = True
            self._keys_pause()

    def done(self, result) -> None:
        super().done(result)
        if self._keys_paused:
            self._keys_paused = False
            self._keys_resume()

    # --------------------------------------------------------------------- field helpers
    def _bind(self, name, getter, setter, value) -> None:
        setter(value)
        self._get[name] = getter

    def _check(self, name: str, label: str) -> QCheckBox:
        box = QCheckBox(label)
        self._bind(name, box.isChecked, box.setChecked, bool(self.values.get(name)))
        return box

    def _choice(self, name: str, options: dict[str, str], editable: bool = False) -> QComboBox:
        """`options`: shown text → stored value."""
        combo = QComboBox()
        combo.setEditable(editable)
        for shown, stored in options.items():
            combo.addItem(shown, stored)
        current = self.values.get(name)
        if combo.findData(current) < 0:
            combo.addItem(str(current), current)

        def get():
            if editable:                         # typed text, unless it is one of the listed
                index = combo.findText(combo.currentText())
                return combo.itemData(index) if index >= 0 else combo.currentText().strip()
            return combo.currentData()

        self._bind(name, get, lambda v: combo.setCurrentIndex(combo.findData(v)), current)
        return combo

    def _device_choice(self, name: str, devices: list[str]) -> QComboBox:
        """A device picked by name: the Windows default (stored blank) first, then
        `devices`. A saved name that is not plugged in is kept, and used again on return."""
        options = {tr("general.mic_default"): ""}
        options.update({device: device for device in devices})
        saved = self.values.get(name, "")
        if saved and saved not in options:
            options[f"{saved} (not connected)"] = saved
        return self._choice(name, options)

    def _text(self, name: str) -> QLineEdit:
        edit = QLineEdit()
        self._bind(name, lambda: edit.text().strip(), edit.setText, str(self.values.get(name, "")))
        return edit

    # ---------------------------------------------------------------------------- tabs
    def _general_tab(self, microphones: list[str]) -> QWidget:
        page, form = QWidget(), QFormLayout()
        page.setLayout(form)
        self.dictation_box = self._check("DICTATION_ON", tr("general.dictation"))
        self.reader_box = self._check("READER_ON", tr("general.reader"))
        self.paused_label = QLabel(tr("general.paused"))
        self.paused_label.setWordWrap(True)
        for box in (self.dictation_box, self.reader_box):
            box.toggled.connect(self._show_paused)
        form.addRow(self.dictation_box)
        form.addRow(self.reader_box)
        form.addRow(self.paused_label)
        self._show_paused()

        self.mic_box = self._device_choice("MICROPHONE", microphones)
        form.addRow(tr("general.mic"), self.mic_box)
        self.language_box = self._choice("INTERFACE_LANGUAGE", {
            tr("lang.auto"): "auto", tr("lang.en"): "en", tr("lang.ar"): "ar"})
        form.addRow(tr("general.language"), self.language_box)
        self.pair_box = self._choice("LANGUAGE_PAIR", {tr("general.pair_en_ar"): "en-ar"})
        form.addRow(tr("general.pair"), self.pair_box)
        self.startup_box = QCheckBox(tr("general.startup"))
        self.startup_box.setChecked(bool(self.startup.get()))
        form.addRow(self.startup_box)
        form.addRow(self._check("KEEP_HISTORY", tr("general.history")))
        form.addRow(self._check("LOG_DICTATION_TEXT", tr("general.logwords")))
        form.addRow(self._check("ENABLE_AUDIO_CHIMES", tr("general.sounds")))
        form.addRow(self._check("ENABLE_TOAST_NOTIFICATIONS", tr("general.notices")))
        form.addRow(QLabel(tr("general.clipboard")))
        self.setup_again_button = QPushButton(tr("general.setup_again"))
        self.setup_again_button.clicked.connect(self._setup_again)
        form.addRow(self.setup_again_button)
        return page

    def _setup_again(self) -> None:
        """Closed first, so its keys come back before the wizard takes them."""
        self.reject()
        self.setup_requested.emit()

    def _show_paused(self) -> None:
        self.paused_label.setVisible(not (self.dictation_box.isChecked()
                                          or self.reader_box.isChecked()))

    def _keys_tab(self) -> QWidget:
        page, form = QWidget(), QFormLayout()
        page.setLayout(form)
        form.addRow(QLabel(tr("keys.hint")))
        self.key_boxes, self.key_notes = {}, {}
        for name, label_key in KEYS:
            self.assigned[tr(label_key)] = str(self.values.get(name, "")).lower()
        for name, label_key in KEYS:
            shown = tr(label_key)
            box = HotkeyEdit(shown, self.assigned, current=self.assigned[shown])
            note = QLabel()
            note.setWordWrap(True)
            note.setVisible(False)
            box.captured.connect(lambda key, s=shown: self.assigned.__setitem__(s, key))
            box.judged.connect(lambda b=box, n=note: (n.setText(b.message_text()),
                                                      n.setVisible(bool(b.message_text()))))
            self.key_boxes[name], self.key_notes[name] = box, note
            self._bind(name, lambda b=box: b.key, lambda v, b=box: (b.setText(v), setattr(b, "key", v)),
                       self.assigned[shown])
            row = QVBoxLayout()
            row.addWidget(box)
            row.addWidget(note)
            form.addRow(shown, row)
        cannot = QLabel(CANNOT_SEE_OTHER_APPS)
        cannot.setWordWrap(True)
        form.addRow(cannot)
        return page

    def _provider_tab(self, ollama_models: list[str], key_saved: bool) -> ProviderPage:
        page = ProviderPage()
        for model in ollama_models:
            page.ollama_model_box.addItem(model)
        page.ollama_model_box.setEditText(self.values.get("OLLAMA_MODEL_NAME", ""))
        page.set_provider(self.values.get("AI_PROVIDER", "builtin"))
        page.url_edit.setText(self.values.get("AI_URL", ""))
        page.model_edit.setText(self.values.get("AI_MODEL", ""))
        page.show_saved_key(key_saved)
        return page

    def _speech_tab(self) -> QWidget:
        page, form = QWidget(), QFormLayout()
        page.setLayout(form)
        form.addRow(tr("speech.whisper"), self._choice(
            "WHISPER_MODEL_NAME", {m: m for m in WHISPER_MODELS}, editable=True))
        form.addRow(tr("speech.device"), self._choice(
            "WHISPER_DEVICE", {"auto": "auto", "cpu": "cpu"}))
        form.addRow(tr("speech.voice"), self._choice("READER_VOICE", {
            label: voice for label, voice in VOICES.items()}))
        speed = QDoubleSpinBox()
        speed.setRange(0.5, 2.0)
        speed.setSingleStep(0.1)
        self._bind("READER_SPEED", lambda: round(speed.value(), 2), speed.setValue,
                   float(self.values.get("READER_SPEED", 1.0)))
        form.addRow(tr("speech.speed"), speed)
        self.output_box = self._device_choice("READER_OUTPUT", self._speakers)
        form.addRow(tr("speech.output"), self.output_box)
        return page

    def _advanced_tab(self) -> QWidget:
        page, form = QWidget(), QFormLayout()
        page.setLayout(form)
        form.addRow(QLabel(tr("adv.restart")))
        form.addRow("Speech precision", self._choice(
            "WHISPER_COMPUTE_TYPE", {c: c for c in COMPUTE_TYPES}))
        seconds = QSpinBox()
        seconds.setRange(1, 3600)
        self._bind("MAX_RECORDING_SECONDS", seconds.value, seconds.setValue,
                   int(self.values.get("MAX_RECORDING_SECONDS", 300)))
        form.addRow("Longest recording (s)", seconds)
        form.addRow("Ollama address", self._text("OLLAMA_HOST_URL"))
        form.addRow("Ollama keep alive", self._text("OLLAMA_KEEP_ALIVE"))
        form.addRow(self._check("AI_LOAD_AT_START", tr("adv.load_ai")))
        form.addRow("Clipboard as context", self._choice("POLISH_CLIPBOARD_CONTEXT", {
            "auto": "auto", "on": "on", "off": "off"}))
        form.addRow("AI build", self._choice("LLAMA_VARIANT", {
            v: v for v in ("auto", "cuda", "vulkan", "cpu")}))
        self.builtin_box = QComboBox()
        for label in BUILTIN_MODELS:
            self.builtin_box.addItem(label)
        form.addRow(tr("adv.builtin"), self.builtin_box)
        form.addRow("Reader device", self._choice("READER_DEVICE", {
            v: v for v in ("auto", "cpu", "cuda")}))
        form.addRow(self._check("READER_SMART_MODE", tr("adv.smart")))
        folder = self._text("MODELS_DIR")
        browse = QPushButton("…")
        browse.clicked.connect(lambda: folder.setText(
            QFileDialog.getExistingDirectory(self, tr("adv.models"), folder.text()) or folder.text()))
        row = QHBoxLayout()
        row.addWidget(folder, 1)
        row.addWidget(browse)
        form.addRow(tr("adv.models"), row)
        return page

    # ------------------------------------------------------------------------- saving
    def collect(self) -> dict:
        """The settings that differ from what the file holds, by their file names. The
        API key is not one of them."""
        new = {name: get() for name, get in self._get.items()}
        page = self.provider_page
        new["AI_PROVIDER"] = page.provider()
        new["AI_URL"] = page.url_edit.text().strip() or self.values.get("AI_URL", "")
        new["AI_MODEL"] = page.model_edit.text().strip()
        new["OLLAMA_MODEL_NAME"] = page.ollama_model_box.currentText().strip()
        repo, filename = BUILTIN_MODELS[self.builtin_box.currentText()]
        if self.values.get("AI_BUILTIN_REPO", repo) in [r for r, _ in BUILTIN_MODELS.values()]:
            new["AI_BUILTIN_REPO"], new["AI_BUILTIN_FILE"] = repo, filename
        return changed_settings(self.values, new)

    def save(self) -> None:
        problems = self.provider_page.problems()
        if problems:
            self._say(problems[0])
            return
        changes = self.collect()
        page = self.provider_page
        key_change = bool(page.key_edit.text()) or page.clear_key_requested
        try:
            if key_change or any(name in changes for name in PROVIDER_SETTINGS):
                save_provider(self.settings_path, self.store, page.provider(),
                              page.url_edit.text().strip() or self.values.get("AI_URL", ""),
                              page.model_edit.text().strip(), page.key_edit.text() or None,
                              clear_key=page.clear_key_requested)
                if "OLLAMA_MODEL_NAME" in changes:
                    storage.update(self.settings_path,
                                   {"OLLAMA_MODEL_NAME": changes["OLLAMA_MODEL_NAME"]})
        except KeyNotSaved as e:
            self.failed.emit(str(e))
            self._say(tr("problem.key") + str(e))
            return
        live = {n: changes.pop(n) for n in LIVE if n in changes}
        file_changes = {n: v for n, v in changes.items() if n not in PROVIDER_SETTINGS}
        if file_changes:
            storage.update(self.settings_path, file_changes)
        if self.startup.get() != self.startup_box.isChecked():
            self.startup.set(self.startup_box.isChecked())
        for name, value in live.items():
            self.apply_live(name, value)
        must_restart = restart_needed(changes)
        self.values.update(live)
        self.values.update(file_changes)
        self._say(tr("saved.restart") if must_restart else tr("saved.live"))
        self.saved.emit(must_restart)
        self.accept()

    def _say(self, text: str) -> None:
        self.status.setText(text)


class StartupKey:
    """Start with Windows: the HKCU Run key, not the settings file."""
    RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
    NAME = "ZeroFlow"

    def __init__(self, command: str):
        self.command = command

    def get(self) -> bool:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN) as key:
                winreg.QueryValueEx(key, self.NAME)
            return True
        except OSError:
            return False

    def set(self, on: bool) -> None:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN, 0, winreg.KEY_SET_VALUE) as key:
            if on:
                winreg.SetValueEx(key, self.NAME, 0, winreg.REG_SZ, self.command)
            else:
                try:
                    winreg.DeleteValue(key, self.NAME)
                except OSError:
                    pass


def startup_command(root: str, executable: str) -> str:
    """The command Windows runs at sign-in: the engine on pythonw, with no console."""
    pythonw = os.path.join(os.path.dirname(executable), "pythonw.exe")
    return f'"{pythonw if os.path.exists(pythonw) else executable}" "{os.path.join(root, "zero_flow.py")}"'


def key_is_saved(store, provider: str, url: str) -> bool:
    address = credentials.provider_address(provider, url)
    try:
        return bool(address and store.get(address))
    except OSError:
        return False
