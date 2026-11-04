"""Polish hands the AI your clipboard as context — but not a cloud AI, unless you say so.

The clipboard often holds what you just copied from a password manager. With a cloud
provider (Claude, or an OpenAI-format service on another computer) Polish sent up to
500 characters of it to that company with every dictation. POLISH_CLIPBOARD_CONTEXT:
"auto" sends it only to an AI on this PC, "on" always, "off" never.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import engine, settings

LOCAL_OPENAI = "http://127.0.0.1:1234/v1/chat/completions"
CLOUD_OPENAI = "https://api.example.com/v1/chat/completions"
LOCAL_OLLAMA = "http://127.0.0.1:11434/api/generate"
REMOTE_OLLAMA = "http://192.168.1.5:11434/api/generate"


def sent(setting, provider, ai_url=LOCAL_OPENAI, ollama_url=LOCAL_OLLAMA):
    return settings.clipboard_context_sent(setting, provider, ai_url, ollama_url)


class TestAuto(unittest.TestCase):
    def test_an_ai_on_this_pc_gets_it(self):
        self.assertTrue(sent("auto", "builtin"))
        self.assertTrue(sent("auto", "ollama"))
        self.assertTrue(sent("auto", "openai", ai_url=LOCAL_OPENAI))

    def test_a_cloud_ai_does_not(self):
        self.assertFalse(sent("auto", "claude"))
        self.assertFalse(sent("auto", "openai", ai_url=CLOUD_OPENAI))

    def test_an_ai_on_another_computer_does_not(self):
        self.assertFalse(sent("auto", "ollama", ollama_url=REMOTE_OLLAMA))
        self.assertFalse(sent("auto", "openai", ai_url="http://my-server:8080/v1"))


class TestOnAndOff(unittest.TestCase):
    def test_on_sends_it_even_to_a_cloud_ai(self):
        self.assertTrue(sent("on", "claude"))

    def test_off_sends_it_nowhere(self):
        self.assertFalse(sent("off", "builtin"))


class TestPolishReadsTheClipboardOnlyWhenAllowed(unittest.TestCase):
    def context(self, allowed, mode="en_polish"):
        with mock.patch.object(engine, "SEND_CLIPBOARD_CONTEXT", allowed), \
             mock.patch.object(engine, "read_clipboard_context",
                               return_value="hunter2") as read:
            return engine.polish_context(mode), read

    def test_allowed(self):
        context, read = self.context(True)
        self.assertEqual(context, "hunter2")

    def test_not_allowed(self):
        context, read = self.context(False)
        self.assertEqual(context, "")
        read.assert_not_called()                  # never even read

    def test_only_polish_uses_it(self):
        context, read = self.context(True, mode="en2ar")
        self.assertEqual(context, "")
        read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
