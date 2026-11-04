"""What you dictate stays out of flow_debug.log unless you ask for it.

The log is for diagnosing the engine, and every dictation went into it word for word —
a dictated password or private note sat there next to the timings. The history file
(flow_history.md) is where dictations are kept; the log records only their size.
LOG_DICTATION_TEXT=true puts the words back, for debugging.
"""
import os
import sys
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import engine, logs, stt, ui
from zeroflow.text import language

SECRET = "my bank pin is 4417"


def whisper_returning(text, language="en"):
    segment = mock.Mock(text=text)
    return mock.Mock(transcribe=mock.Mock(return_value=(iter([segment]),
                                                        mock.Mock(language=language))))


class TestDictationIsNotLogged(unittest.TestCase):
    def dictate(self):
        """One raw English dictation of SECRET, through transcribe → inject; the log."""
        with mock.patch.object(stt, "model", whisper_returning(f" {SECRET}")), \
             mock.patch.object(stt, "model_runtime", "CPU · int8"), \
             mock.patch.object(stt, "load_vocabulary", return_value=[]), \
             mock.patch.object(engine, "ENABLE_AUDIO_CHIMES", False), \
             mock.patch.object(ui, "update_console_title"), \
             mock.patch.object(engine, "paste_text") as paste, \
             mock.patch.object(engine, "log_to_history"), \
             mock.patch("zeroflow.text.macros.load_vocabulary", return_value=[]), \
             mock.patch("sys.stdout"), \
             self.assertLogs(level="INFO") as captured:
            engine.transcribe_and_inject(np.full((16000, 1), 0.1, np.float32), "en_raw", "")
        paste.assert_called_once()
        self.assertIn(SECRET, paste.call_args.args[0])          # it was still pasted
        return "\n".join(captured.output)

    def test_the_words_are_not_in_the_log(self):
        with mock.patch.object(logs, "LOG_DICTATION_TEXT", False):
            log = self.dictate()
        self.assertNotIn("4417", log)
        self.assertIn(f"{len(SECRET)} chars", log)             # its size still is

    def test_the_setting_puts_them_back(self):
        with mock.patch.object(logs, "LOG_DICTATION_TEXT", True):
            log = self.dictate()
        self.assertIn(SECRET, log)


class TestTheLanguageGuardDoesNotLogTheAnswer(unittest.TestCase):
    def test_a_wrong_language_answer_is_not_logged(self):
        answer = "我的银行密码是 4417"              # Chinese for an English Polish
        with mock.patch.object(logs, "LOG_DICTATION_TEXT", False), \
             mock.patch("sys.stdout"), \
             self.assertLogs(level="WARNING") as captured:
            out = language.checked_ai_output(answer, SECRET, "en")
        self.assertEqual(out, SECRET)
        self.assertNotIn("4417", "\n".join(captured.output))


class TestSaid(unittest.TestCase):
    def test_hidden_by_default(self):
        with mock.patch.object(logs, "LOG_DICTATION_TEXT", False):
            self.assertEqual(logs.said("hello"), "(5 chars)")

    def test_shown_when_asked(self):
        with mock.patch.object(logs, "LOG_DICTATION_TEXT", True):
            self.assertEqual(logs.said("hello"), "'hello'")

    def test_nothing_is_nothing(self):
        self.assertEqual(logs.said(None), "None")


if __name__ == "__main__":
    unittest.main()
