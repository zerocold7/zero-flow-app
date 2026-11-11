"""The Qt interface, on the Engine's main thread (ADR 0001): the tray icon and its menu,
the overlay, and the Settings window. It replaces pystray.

Other threads (the keyboard hook, workers, the Reader's state) reach it only through
Qt signals (`UiBridge`), never by touching a widget. Switching a half on or off loads or
frees models, so it runs on a worker thread, never on this one.
"""
import logging
import os
import sys
import threading

import sounddevice as sd
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from zeroflow import credentials, engine, i18n, microphone, paths, settings, signals, storage, ui
from zeroflow.halves import Halves
from zeroflow.i18n import tr
from zeroflow.overlay import Overlay, UiBridge
from zeroflow.paths import BASE_DIR
from zeroflow.settings_window import (KEYS, SettingsWindow, StartupKey, key_is_saved,
                                      startup_command)

READING_POLL_MS = 150


def microphone_names() -> list[str]:
    try:
        return microphone.input_names(sd.query_devices())
    except Exception:
        return []


def ollama_models() -> list[str]:
    """The models Ollama has installed, for the picker; [] when it is not running."""
    try:
        import requests
        base = settings.OLLAMA_HOST_URL.split("/api/")[0]
        answer = requests.get(f"{base}/api/tags", timeout=0.6).json()
        return [m["name"] for m in answer.get("models", [])]
    except Exception:
        return []


def shown_keys() -> list[tuple[str, str]]:
    """Every key as (what it does, the key), for the tray's Keys menu."""
    by_name = {name: settings.HOTKEYS[action]
               for action, (name, _) in settings._HOTKEY_SETTINGS.items()}
    by_name["HOTKEY_READ"] = settings.HOTKEY_READ
    rows = [(tr(label), by_name[name].upper()) for name, label in KEYS]
    return rows + [(tr("keys.cancel"), settings.CANCEL_KEY.upper())]


class EngineApp:
    def __init__(self, dictation, reader, restart_engine, quit_engine, banner=None):
        i18n.choose(settings.INTERFACE_LANGUAGE)
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.app.setApplicationName("Zero- Flow")
        self.app.setQuitOnLastWindowClosed(False)
        if i18n.is_rtl():
            self.app.setLayoutDirection(Qt.RightToLeft)
        self.icon = QIcon(os.path.join(BASE_DIR, "logo_tray.ico"))
        self.restart_engine, self.quit_engine = restart_engine, quit_engine
        self.dictation, self.reader, self.banner = dictation, reader, banner

        self.bridge = UiBridge()
        ui.bridge = self.bridge
        self.overlay = Overlay()
        self.bridge.status.connect(self.overlay.show_state)
        self.bridge.level.connect(self.overlay.set_level)
        self.bridge.cleared.connect(self._cleared)
        self.bridge.detail.connect(self.overlay.set_detail)

        self.halves = Halves(dictation, reader, save=self._save_switch)
        self.halves.changed.connect(self._refresh_tray)
        self.halves.problem.connect(lambda text: ui.show_toast("⚠️ Zero- Flow", text))
        self.window = None
        self.wizard = None
        self._build_tray()
        self._reading = QTimer()
        self._reading.timeout.connect(self._follow_reader)
        self._reading.start(READING_POLL_MS)

    # --------------------------------------------------------------------------- tray
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.icon)
        menu = QMenu()
        self.title_action = QAction(menu)
        self.title_action.setEnabled(False)
        self.dictation_action = QAction(tr("tray.dictation"), menu, checkable=True)
        self.reader_action = QAction(tr("tray.reader"), menu, checkable=True)
        self.dictation_action.triggered.connect(lambda on: self._worker(self.halves.set_dictation, on))
        self.reader_action.triggered.connect(lambda on: self._worker(self.halves.set_reader, on))
        settings_action = QAction(tr("tray.settings"), menu)
        settings_action.triggered.connect(self.open_settings)
        unload_action = QAction(tr("tray.unload"), menu)
        unload_action.triggered.connect(lambda: self._worker(engine.unload_ai_model))
        logs_action = QAction(tr("tray.logs"), menu)
        logs_action.triggered.connect(lambda: os.startfile(paths.ready_log_dir()))
        exit_action = QAction(tr("tray.exit"), menu)
        exit_action.triggered.connect(self._exit)
        for action in (self.title_action, self.dictation_action, self.reader_action):
            menu.addAction(action)
        keys_menu = menu.addMenu(tr("tray.keys"))
        for shown, key in shown_keys():
            keys_menu.addAction(f"{shown}    {key}").setEnabled(False)
        menu.addSeparator()
        for action in (settings_action, unload_action, logs_action):
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(exit_action)
        self.tray.setContextMenu(menu)
        self.menu = menu                     # kept: the tray does not own it
        self.tray.activated.connect(lambda reason: reason == QSystemTrayIcon.DoubleClick
                                    and self.open_settings())
        self._refresh_tray()
        self.tray.show()

    def _refresh_tray(self) -> None:
        self.dictation_action.setChecked(self.halves.dictation_on)
        self.reader_action.setChecked(self.halves.reader_on)
        text = tr(f"tray.{self.halves.state}")
        self.title_action.setText(text)
        self.tray.setToolTip(text)

    def _exit(self) -> None:
        self.tray.hide()
        self.quit_engine()

    @staticmethod
    def _worker(fn, *args) -> None:
        threading.Thread(target=fn, args=args, daemon=True).start()

    # ------------------------------------------------------------------------ overlay
    def _cleared(self) -> None:
        if not signals.is_reading():
            self.overlay.hide_overlay()

    def _follow_reader(self) -> None:
        """The Reader is another process: its "speaking" flag drives the Reading state."""
        reading = signals.is_reading()
        if reading and self.overlay.state is None:
            self.overlay.show_state("reading")
        elif not reading and self.overlay.state == "reading":
            self.overlay.hide_overlay()

    # ---------------------------------------------------------------- settings window
    @staticmethod
    def _save_switch(name: str, value: bool) -> None:
        storage.update(settings.SETTINGS_FILE, {name: value})

    def open_settings(self) -> None:
        if settings.NEEDS_SETUP:                  # no settings file yet: the wizard makes it
            self.open_setup(first_start=True)
            return
        if self.window is not None and self.window.isVisible():
            self.window.raise_()
            self.window.activateWindow()
            return
        values, _ = settings.resolve(storage.load(settings.SETTINGS_FILE))
        values["DICTATION_ON"], values["READER_ON"] = self.halves.dictation_on, self.halves.reader_on
        store = credentials.WindowsStore()
        self.window = SettingsWindow(
            values, settings.SETTINGS_FILE, store, microphone_names(),
            StartupKey(startup_command(BASE_DIR, sys.executable)), self._apply_live,
            ollama_models(), key_saved=key_is_saved(store, values["AI_PROVIDER"], values["AI_URL"]),
            keys_pause=self._pause_keys, keys_resume=self._resume_keys)
        self.window.saved.connect(lambda restart: restart and QTimer.singleShot(300, self.restart_engine))
        self.window.setup_requested.connect(lambda: self.open_setup(first_start=False))
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    # ------------------------------------------------------------------ first-run wizard
    def open_setup(self, first_start: bool) -> None:
        """The wizard (zeroflow/wizard.py). Finishing writes the settings file and
        restarts the Engine, so every setting is read fresh. Closed on a first start, it
        writes nothing and the Engine ends: the next start opens it again."""
        if self.wizard is not None and self.wizard.isVisible():
            self.wizard.raise_()
            self.wizard.activateWindow()
            return
        from zeroflow.wizard import SetupWizard
        self.wizard = SetupWizard(settings.SETTINGS_FILE, credentials.WindowsStore(),
                                  microphone_names(), keys_pause=self._pause_keys,
                                  keys_resume=self._resume_keys, ollama_models=ollama_models())
        if not first_start:
            self.wizard.load_current()
        self.wizard.completed.connect(lambda: QTimer.singleShot(300, self.restart_engine))
        if first_start:
            self.wizard.rejected.connect(self._exit)
        self.wizard.show()
        self.wizard.raise_()
        self.wizard.activateWindow()

    def _pause_keys(self) -> None:
        signals.set_keys_paused(True)             # the Reader process lets go of its keys
        engine.pause_hotkeys()

    def _resume_keys(self) -> None:
        signals.set_keys_paused(False)
        if self.dictation.running:
            engine.resume_hotkeys()

    def _apply_live(self, name: str, value: bool) -> None:
        set_half = self.halves.set_dictation if name == "DICTATION_ON" else self.halves.set_reader
        self._worker(set_half, value)

    # --------------------------------------------------------------------------- start
    def boot(self, dictation_on: bool, reader_on: bool) -> None:
        """Worker thread: load what is switched on, then tell the interface."""
        try:
            engine.boot(load=False)
            if dictation_on:
                self.dictation.start()
            if reader_on:
                self.reader.start()
        except Exception:
            engine.report_fatal_error("engine")
            self.quit_engine(1)
            return
        logging.info(f"Engine is up ({self.halves.state}).")
        if self.banner:                       # only does anything when there is a console
            try:
                self.banner()
            except Exception:
                logging.warning("The console banner could not be shown.", exc_info=True)
        self.bridge.booted.emit()

    def run(self) -> None:
        if settings.NEEDS_SETUP:
            # A first start with nothing to migrate: nothing loads until the wizard has
            # written the settings file and restarted the Engine.
            logging.info("First start: opening the setup wizard.")
            QTimer.singleShot(0, lambda: self.open_setup(first_start=True))
        else:
            self.bridge.booted.connect(self._booted)
            threading.Thread(target=self.boot, args=(settings.DICTATION_ON, settings.READER_ON),
                             daemon=True).start()
        self.app.exec()

    def _booted(self) -> None:
        self._refresh_tray()
        self.halves.state_changed.emit(self.halves.state)
        if self.halves.state == "active":
            ui.show_toast("🚀 Zero- Flow", tr("tray.active"), settings.ENABLE_TOASTS)


def run(dictation, reader, restart_engine, quit_engine, banner=None) -> None:
    EngineApp(dictation, reader, restart_engine, quit_engine, banner).run()
