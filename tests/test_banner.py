"""The start-up banners show the keys you actually have — read from .env, never typed
in by hand. Each test sets unusual keys, so a banner with a hard-coded "F5" fails."""
import contextlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reader import app as reader_app
from zeroflow import engine, supervisor, ui

KEYS = {name: f"ctrl+alt+{n}" for n, name in enumerate(
    ["en_raw", "en_polish", "ar_raw", "ar_polish", "en2ar", "ar2en",
     "fix", "maintenance", "purge", "panic"])}


class BannerTestCase(unittest.TestCase):
    def shown(self, show):
        console = io.StringIO()
        with mock.patch.object(ui.os, "system"), mock.patch.object(ui.time, "sleep"), \
             mock.patch.object(engine, "get_ollama_model", return_value="some-model"), \
             contextlib.redirect_stdout(console):
            show()
        return console.getvalue()


class TestBanners(BannerTestCase):
    def test_the_dictation_banner_shows_every_dictation_key(self):
        with mock.patch.object(engine, "HOTKEYS", KEYS):
            text = self.shown(engine.show_banner)
        for key in KEYS.values():
            self.assertIn(key.upper(), text)
        self.assertIn("some-model", text)

    def test_the_whole_engine_banner_adds_the_read_key(self):
        with mock.patch.object(engine, "HOTKEYS", KEYS), \
             mock.patch.object(supervisor.settings, "HOTKEY_READ", "ctrl+alt+r"):
            text = self.shown(supervisor.show_banner)
        for key in [*KEYS.values(), "ctrl+alt+r"]:
            self.assertIn(key.upper(), text)
        self.assertIn("Kokoro", text)

    def test_the_reader_banner_shows_its_keys(self):
        with mock.patch.object(reader_app, "HOTKEY_READ", "ctrl+alt+r"), \
             mock.patch.object(reader_app, "HOTKEY_PANIC", "ctrl+alt+s"):
            text = self.shown(reader_app.print_boot_sequence)
        self.assertIn("CTRL+ALT+R", text)
        self.assertIn("CTRL+ALT+S", text)


if __name__ == "__main__":
    unittest.main()
