"""The Claude provider (AI_PROVIDER="claude"): Anthropic's API, with the user's own key.
The SDK client is replaced by a stand-in — no request leaves this PC, nothing is billed."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anthropic
import httpx2

from zeroflow import llm
from zeroflow.llm import claude


def reply(*texts, stop_reason="end_turn", thinking=True):
    blocks = [SimpleNamespace(type="thinking", thinking="")] if thinking else []
    blocks += [SimpleNamespace(type="text", text=t) for t in texts]
    return SimpleNamespace(content=blocks, stop_reason=stop_reason, stop_details=None)


def api_error(cls, status):
    response = httpx2.Response(status, request=httpx2.Request("POST", "https://api.anthropic.com"))
    return cls("rejected", response=response, body=None)


class ClaudeTestCase(unittest.TestCase):
    def setUp(self):
        self.client = mock.Mock()
        self.client.with_options.return_value = self.client   # per-request timeout
        for patcher in (mock.patch.object(claude, "_make_client", return_value=self.client),
                        mock.patch.object(claude, "_clients", {}),
                        mock.patch.object(claude, "AI_MODEL", ""),
                        mock.patch.object(claude, "AI_API_KEY", "sk-ant-test"),
                        mock.patch.object(claude, "ENABLE_TOASTS", False),
                        mock.patch.object(claude.ui, "start_processing_spinner"),
                        mock.patch.object(claude.ui, "stop_processing_spinner")):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.create = self.client.beta.messages.create

    def sent(self):
        return self.create.call_args.kwargs


class TestRequest(ClaudeTestCase):
    def test_a_polish_request(self):
        self.create.return_value = reply("The meeting is at ten.")
        answer = claude.ask("so um the meeting is at ten", "clipboard text", "Polish this.")
        self.assertEqual(answer, "The meeting is at ten.")
        sent = self.sent()
        self.assertEqual(sent["model"], "claude-opus-5-5")
        self.assertEqual(sent["system"], "Polish this.")
        user = sent["messages"][0]
        self.assertEqual(user["role"], "user")
        self.assertIn("so um the meeting is at ten", user["content"])
        self.assertIn("clipboard text", user["content"])

    def test_quick_clean_up_settings_for_the_current_model(self):
        """Low effort for short clean-up; no temperature or thinking switch, which
        this model rejects; the refusal fallback on."""
        self.create.return_value = reply("Done.")
        claude.ask("hello", None, "Polish this.")
        sent = self.sent()
        self.assertEqual(sent.get("output_config"), {"effort": "low"})
        self.assertEqual(sent.get("fallbacks"), "default", "the refusal fallback is off")
        self.assertIn("server-side-fallback-2026-07-01", sent["betas"])
        self.assertNotIn("temperature", sent)
        self.assertNotIn("thinking", sent)
        self.assertGreaterEqual(sent["max_tokens"], 4096)

    def test_a_model_chosen_in_env_is_used(self):
        self.create.return_value = reply("Done.")
        with mock.patch.object(claude, "AI_MODEL", "claude-haiku-5-5"):
            claude.ask("hello", None, "Polish this.")
        self.assertEqual(self.sent()["model"], "claude-haiku-5-5")

    def test_the_key_from_env_is_used(self):
        claude._get_client()
        claude._make_client.assert_called_with("sk-ant-test")

    def test_learned_words_are_taken_from_the_answer(self):
        self.create.return_value = reply("Ask Tamara. [LEARN: Tamara]")
        with mock.patch.object(claude, "_absorb_learned_word",
                               side_effect=lambda out, heard: "Ask Tamara.") as absorb:
            self.assertEqual(claude.ask("ask tamara", None, "Polish."), "Ask Tamara.")
        self.assertEqual(absorb.call_args.kwargs["heard"], "ask tamara")


class TestNoAnswer(ClaudeTestCase):
    def assert_no_answer(self, logged):
        with self.assertLogs(level="WARNING") as logs:
            self.assertIsNone(claude.ask("hello", None, "Polish this."))
        self.assertIn(logged, "\n".join(logs.output))

    def test_a_refusal_is_no_answer(self):
        self.create.return_value = reply(stop_reason="refusal")
        self.assert_no_answer("declined")

    def test_a_rejected_key_says_so(self):
        self.create.side_effect = api_error(anthropic.AuthenticationError, 401)
        self.assert_no_answer("API key")

    def test_rate_limits_and_outages_are_no_answer(self):
        for error in (api_error(anthropic.RateLimitError, 429),
                      api_error(anthropic.InternalServerError, 500),
                      anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com"))):
            self.create.side_effect = error
            self.assert_no_answer("Claude")

    def test_an_empty_answer_is_no_answer(self):
        self.create.return_value = reply("   ")
        self.assert_no_answer("empty")


class TestChoosing(unittest.TestCase):
    def test_claude_is_a_provider(self):
        self.assertIs(llm.choose("claude"), claude)


if __name__ == "__main__":
    unittest.main()
