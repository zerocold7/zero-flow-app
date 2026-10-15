"""Unloading the AI model: a tray item frees its memory, and the next request that needs
it loads it again by itself. AI_LOAD_AT_START=False skips loading it at start-up."""
import contextlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_builtin_ai import BuiltinTestCase
from zeroflow import engine, llm, signals
from zeroflow.llm import builtin, claude, ollama, openai_compatible


class TestEveryProviderCanUnload(unittest.TestCase):
    def test_the_call_reaches_the_active_provider(self):
        fake = mock.Mock(unload=mock.Mock(return_value=True))
        with mock.patch.object(llm, "provider", fake):
            self.assertTrue(llm.unload_ai())
        fake.unload.assert_called_once()

    def test_a_cloud_ai_has_nothing_on_this_pc_to_unload(self):
        self.assertFalse(openai_compatible.unload())
        self.assertFalse(claude.unload())


class TestBuiltinUnload(BuiltinTestCase):
    def test_unloading_stops_the_server_and_the_next_request_loads_it_again(self):
        self.assertEqual(builtin.ask("hello", None, "Polish."), "Answer to: hello")
        self.assertTrue(builtin.unload())
        self.assertFalse(builtin._healthy(), "the server still answers: nothing was freed")
        self.assertEqual(builtin.ask("again", None, "Polish."), "Answer to: again")

    def test_nothing_running_means_nothing_unloaded(self):
        self.assertFalse(builtin.unload())


class TestOllamaUnload(unittest.TestCase):
    def test_ollama_is_told_to_drop_the_model_now(self):
        reply = mock.Mock(status_code=200)
        with mock.patch.object(ollama, "_ollama_model", "some-model"), \
             mock.patch.object(ollama.requests, "post", return_value=reply) as post:
            self.assertTrue(ollama.unload())
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["model"], "some-model")
        self.assertEqual(body["keep_alive"], 0)

    def test_ollama_not_running_is_not_an_error(self):
        with mock.patch.object(ollama, "_ollama_model", "some-model"), \
             mock.patch.object(ollama.requests, "post", side_effect=ConnectionError("refused")):
            self.assertFalse(ollama.unload())


class TestTheSignal(unittest.TestCase):
    def test_a_request_reaches_the_engine_once(self):
        """The full engine's tray belongs to the reader process; the AI to the engine."""
        if not signals.available():
            self.skipTest("Windows signalling unavailable")
        while signals.wait_for_ai_unload(0):             # start from a clear state
            pass
        signals.request_ai_unload()
        self.assertTrue(signals.wait_for_ai_unload(0))
        self.assertFalse(signals.wait_for_ai_unload(0), "one request, one unload")


class TestTheEngine(unittest.TestCase):
    def console(self):
        return contextlib.redirect_stdout(io.StringIO())

    def test_unloading_says_what_happened(self):
        out = io.StringIO()
        with mock.patch.object(engine, "unload_ai", return_value=True), \
             contextlib.redirect_stdout(out):
            engine.unload_ai_model()
        self.assertIn("unloaded", out.getvalue().lower())

    def threads_started_by_boot(self, load_at_start):
        started = []
        with mock.patch.object(engine, "AI_LOAD_AT_START", load_at_start), \
             mock.patch.object(engine.threading, "Thread",
                               side_effect=lambda target, **kw: started.append(target) or mock.Mock()), \
             mock.patch.object(engine.stt, "load_whisper_model"), \
             mock.patch.object(engine, "cap_history_file"), \
             mock.patch.object(engine.signals, "set_recording"), \
             mock.patch.object(engine.ui, "update_console_title"), \
             mock.patch.object(engine.ui, "report_setting_problems"), \
             self.console():
            engine.boot()
        return started

    def test_the_ai_loads_at_start_by_default(self):
        self.assertIn(engine.warm_up_ai, self.threads_started_by_boot(True))

    def test_ai_load_at_start_false_leaves_it_for_the_first_polish(self):
        self.assertNotIn(engine.warm_up_ai, self.threads_started_by_boot(False))

    def test_the_engine_listens_for_unload_requests(self):
        self.assertIn(engine.watch_for_unload_requests, self.threads_started_by_boot(False))


class TestTheTrayItem(unittest.TestCase):
    def test_the_reader_tray_offers_it(self):
        from reader import app
        labels = [str(item.text) for item in app.tray_items() if hasattr(item, "text")]
        self.assertIn("Unload AI model", labels)

    def test_the_reader_unloads_its_own_and_asks_the_engine(self):
        from reader import app
        with mock.patch.object(app.llm, "unload_ai", return_value=False) as own, \
             mock.patch.object(app.signals, "request_ai_unload") as ask_engine, \
             contextlib.redirect_stdout(io.StringIO()):
            app.unload_ai_model(None, None)
        own.assert_called_once()
        ask_engine.assert_called_once()


if __name__ == "__main__":
    unittest.main()
