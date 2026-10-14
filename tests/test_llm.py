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


class TestChoosingAProvider(unittest.TestCase):
    def test_a_provider_is_chosen_by_name(self):
        from zeroflow.llm import openai_compatible
        self.assertIs(llm.choose("openai"), openai_compatible)
        self.assertIs(llm.choose("ollama"), llm.ollama)

    def test_an_unknown_name_is_reported_and_ollama_used(self):
        with mock.patch.object(llm.settings, "problems", []):
            self.assertIs(llm.choose("chatgpt"), llm.ollama)
            self.assertEqual(len(llm.settings.problems), 1, "the mistake was not reported")
            self.assertIn('AI_PROVIDER="chatgpt"', llm.settings.problems[0])


class TestOpenAICompatible(unittest.TestCase):
    """LM Studio, the llama.cpp server, OpenAI, Groq…: one chat/completions format."""

    def setUp(self):
        from zeroflow.llm import openai_compatible as provider
        self.provider = provider
        for patcher in (mock.patch.object(provider, "AI_URL", "http://127.0.0.1:8080/v1/chat/completions"),
                        mock.patch.object(provider, "AI_MODEL", "local-model"),
                        mock.patch.object(provider, "AI_API_KEY", ""),
                        mock.patch.object(provider, "ENABLE_TOASTS", False),
                        mock.patch.object(provider.ui, "start_processing_spinner"),
                        mock.patch.object(provider.ui, "stop_processing_spinner")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def reply(self, status=200, content="Polished."):
        body = {"choices": [{"message": {"content": content}}]}
        return mock.Mock(status_code=status, json=lambda: body, text="error text")

    def test_the_request_is_a_chat_with_the_instruction_as_system(self):
        with mock.patch.object(self.provider.requests, "post", return_value=self.reply()) as post:
            answer = self.provider.ask("so um hello", "clipboard text", "Polish this.")
        self.assertEqual(answer, "Polished.")
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["model"], "local-model")
        self.assertEqual(body["messages"][0], {"role": "system", "content": "Polish this."})
        self.assertIn("so um hello", body["messages"][1]["content"])
        self.assertIn("clipboard text", body["messages"][1]["content"])
        self.assertNotIn("Authorization", post.call_args.kwargs.get("headers") or {})

    def test_a_key_is_sent_only_when_set(self):
        with mock.patch.object(self.provider, "AI_API_KEY", "sk-test"), \
             mock.patch.object(self.provider.requests, "post", return_value=self.reply()) as post:
            self.provider.ask("hello", None, "Polish this.")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer sk-test")

    def test_no_answer_is_none_with_the_reason_logged(self):
        for outcome in (self.reply(status=500), self.reply(content="   "), ConnectionError("refused")):
            kwargs = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
            with mock.patch.object(self.provider.requests, "post", **kwargs), \
                 self.assertLogs(level="WARNING"):
                self.assertIsNone(self.provider.ask("hello", None, "Polish this."))

    def test_learned_words_are_taken_from_the_answer(self):
        reply = self.reply(content="Ask Tamara. [LEARN: Tamara]")
        with mock.patch.object(self.provider.requests, "post", return_value=reply), \
             mock.patch.object(self.provider, "_absorb_learned_word",
                               side_effect=lambda out, heard: "Ask Tamara.") as absorb:
            self.assertEqual(self.provider.ask("ask tamara", None, "Polish this."), "Ask Tamara.")
        self.assertEqual(absorb.call_args.kwargs["heard"], "ask tamara")


if __name__ == "__main__":
    unittest.main()
