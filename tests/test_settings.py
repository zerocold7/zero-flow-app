"""Settings from .env: a value that is not what the setting needs is reported by
name, and the engine carries on with the default — it used to crash on start with a
traceback, unseen when started hidden."""
import contextlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import engine, settings


class SettingsTestCase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(settings, "problems", [])
        patcher.start()
        self.addCleanup(patcher.stop)

    def env(self, **values):
        return mock.patch.dict(os.environ, {k: str(v) for k, v in values.items()})


class TestReading(SettingsTestCase):
    def test_numbers(self):
        with self.env(SOME_SECONDS="2.5", SOME_COUNT="7"):
            self.assertEqual(settings.number("SOME_SECONDS", 300), 2.5)
            self.assertEqual(settings.whole_number("SOME_COUNT", 1), 7)
        self.assertEqual(settings.problems, [])

    def test_yes_and_no_in_every_usual_spelling(self):
        for spelled, meaning in (("True", True), ("yes", True), ("1", True), ("ON", True),
                                 ("false", False), ("No", False), ("0", False), ("off", False)):
            with self.env(SOME_SWITCH=spelled):
                self.assertIs(settings.switch("SOME_SWITCH", not meaning), meaning, spelled)

    def test_a_missing_or_blank_setting_takes_its_default(self):
        with self.env(SOME_COUNT=""):
            self.assertEqual(settings.whole_number("SOME_COUNT", 8192), 8192)
        self.assertEqual(settings.whole_number("SURELY_NOT_SET_ANYWHERE", 5), 5)
        self.assertEqual(settings.problems, [])

    def test_choices(self):
        with self.env(SOME_DEVICE=" CPU "):
            self.assertEqual(settings.choice("SOME_DEVICE", "auto", ("auto", "cpu")), "cpu")


class TestMistakes(SettingsTestCase):
    def test_a_word_where_a_number_belongs_is_reported_and_the_default_used(self):
        with self.env(MAX_RECORDING_SECONDS="five"):
            self.assertEqual(settings.number("MAX_RECORDING_SECONDS", 300, minimum=1), 300)
        self.assertEqual(len(settings.problems), 1)
        self.assertIn('MAX_RECORDING_SECONDS="five"', settings.problems[0])
        self.assertIn("300", settings.problems[0])

    def test_a_number_out_of_range_is_reported(self):
        with self.env(OLLAMA_NUM_CTX="-4"):
            self.assertEqual(settings.whole_number("OLLAMA_NUM_CTX", 8192, minimum=0), 8192)
        self.assertIn("OLLAMA_NUM_CTX", settings.problems[0])

    def test_an_unknown_switch_value_is_reported(self):
        with self.env(ENABLE_AUDIO_CHIMES="maybe"):
            self.assertIs(settings.switch("ENABLE_AUDIO_CHIMES", True), True)
        self.assertIn("ENABLE_AUDIO_CHIMES", settings.problems[0])

    def test_an_unknown_choice_is_reported(self):
        with self.env(WHISPER_DEVICE="gpu"):
            self.assertEqual(settings.choice("WHISPER_DEVICE", "auto", ("auto", "cpu")), "auto")
        self.assertIn('"gpu"', settings.problems[0])


class TestStartUp(SettingsTestCase):
    def test_the_engine_reports_mistakes_when_it_starts(self):
        settings.problems.append('MAX_RECORDING_SECONDS="five" is not a number — using 300.')
        console = io.StringIO()
        with mock.patch.object(engine.stt, "load_whisper_model"), \
             mock.patch.object(engine, "warm_up_ai"), \
             mock.patch.object(engine, "cap_history_file"), \
             mock.patch.object(engine.signals, "set_recording"), \
             mock.patch.object(engine.ui, "update_console_title"), \
             mock.patch.object(engine.ui, "show_toast") as toast, \
             contextlib.redirect_stdout(console), \
             self.assertLogs(level="WARNING") as logs:
            engine.boot()
        self.assertIn("MAX_RECORDING_SECONDS", console.getvalue())
        self.assertIn("MAX_RECORDING_SECONDS", "\n".join(logs.output))
        toast.assert_called()


if __name__ == "__main__":
    unittest.main()
