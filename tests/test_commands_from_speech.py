"""Spoken commands come from what you said, never from the AI's answer.

"New line" at the start of a dictation sends Shift+Enter. The commands used to be read
from the text after Polish or Translate, so the AI decided: text on the clipboard,
handed to Polish as context, could steer its answer, and Translate translated
"سطر جديد" away, so the new line you asked for never came.

Now the command is taken off the transcript first; the AI only sees the words after
it, and its answer is pasted after the key you spoke.
"""
import os
import sys
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import engine, stt, ui


def whisper_returning(text, language="en"):
    segment = mock.Mock(text=text)
    return mock.Mock(transcribe=mock.Mock(return_value=(iter([segment]),
                                                        mock.Mock(language=language))))


class DictationTestCase(unittest.TestCase):
    def dictate(self, said, mode, answer):
        """Dictate `said` in `mode` with the AI answering `answer`. Returns (what the AI
        was given, the paste_text call, whether Shift+Enter was sent first)."""
        given = []

        def fake_ai(raw, context, prompt, **kw):
            given.append(raw)
            return answer
        lang = "ar" if mode.startswith("ar") else "en"
        with mock.patch.object(stt, "model", whisper_returning(f" {said}", lang)), \
             mock.patch.object(stt, "model_runtime", "CPU · int8"), \
             mock.patch.object(stt, "load_vocabulary", return_value=[]), \
             mock.patch.object(engine, "ask_ai", side_effect=fake_ai), \
             mock.patch.object(engine, "ENABLE_AUDIO_CHIMES", False), \
             mock.patch.object(engine, "ENABLE_TOASTS", False), \
             mock.patch.object(ui, "update_console_title"), \
             mock.patch.object(engine, "paste_text") as paste, \
             mock.patch.object(engine.keyboard, "send") as keys, \
             mock.patch.object(engine, "log_to_history"), \
             mock.patch("zeroflow.text.macros.load_vocabulary", return_value=[]), \
             mock.patch("sys.stdout"):
            engine.transcribe_and_inject(np.full((16000, 1), 0.1, np.float32), mode, "")
        shift_enter = mock.call("shift+enter") in keys.call_args_list
        return given, paste.call_args, shift_enter


class TestTheAICannotAddACommand(DictationTestCase):
    def test_an_answer_starting_with_new_line_does_not_add_one(self):
        _, _, shift_enter = self.dictate("see you tomorrow", "en_polish",
                                         "New line. See you tomorrow.")
        self.assertFalse(shift_enter)


class TestYourCommandStillWorks(DictationTestCase):
    def test_new_line_you_said_survives_polish(self):
        given, paste, shift_enter = self.dictate("new line see you tomorrow", "en_polish",
                                                 "See you tomorrow.")
        self.assertTrue(shift_enter)
        self.assertEqual(given, ["see you tomorrow"])          # the AI never saw it
        self.assertEqual(paste.args[0], "See you tomorrow.")

    def test_new_line_you_said_survives_translate(self):
        given, paste, shift_enter = self.dictate("سطر جديد مرحبا بك", "ar2en", "Welcome.")
        self.assertTrue(shift_enter)
        self.assertEqual(given, ["مرحبا بك"])

    def test_raw_mode_is_unchanged(self):
        given, paste, shift_enter = self.dictate("new line see you tomorrow", "en_raw", None)
        self.assertEqual(given, [])                             # no AI in raw mode
        self.assertTrue(shift_enter)
        self.assertEqual(paste.args[0], "see you tomorrow")


if __name__ == "__main__":
    unittest.main()
