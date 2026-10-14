"""zeroflow.llm hands every call to the active provider — so a second provider (the
built-in model of phase 4) needs no change in the engine or the reader."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import llm


class FakeProvider:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []
        self.warmed = False

    def ask(self, raw_text, context_text, instruction, timeout=15.0):
        self.calls.append((raw_text, context_text, instruction, timeout))
        return self.answer

    def warm_up(self):
        self.warmed = True

    def model_name(self):
        return "fake-model"


class TestRouting(unittest.TestCase):
    def use(self, answer):
        fake = FakeProvider(answer)
        patcher = mock.patch.object(llm, "provider", fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fake

    def test_every_call_reaches_the_active_provider(self):
        fake = self.use("Polished.")
        self.assertEqual(llm.ask_ai("raw", "ctx", "Polish.", timeout=3), "Polished.")
        self.assertEqual(fake.calls, [("raw", "ctx", "Polish.", 3)])
        llm.warm_up_ai()
        self.assertTrue(fake.warmed)
        self.assertEqual(llm.model_name(), "fake-model")

    def test_query_falls_back_to_the_original_when_there_is_no_answer(self):
        self.use(None)
        self.assertIsNone(llm.ask_ai("raw", None, "Polish."))
        self.assertEqual(llm.query_ai("raw", None, "Polish."), "raw")

    def test_ollama_is_the_provider_today(self):
        from zeroflow.llm import ollama
        self.assertIs(llm.provider, ollama)
        for name in ("ask", "warm_up", "model_name"):
            self.assertTrue(callable(getattr(ollama, name)), name)


if __name__ == "__main__":
    unittest.main()
