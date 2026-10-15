"""The built-in AI: the engine runs llama-server itself, as a hidden child process.

These start a real process — tests/fake_llama_server.py, which answers like
llama-server without loading a model — so starting, waiting until it is ready,
sharing one server, a crash and a missing runtime are tested as they really happen.
"""
import os
import socket
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from zeroflow import llm
from zeroflow.llm import builtin
from zeroflow.llm import llama_runtime as rt

FAKE = [sys.executable, os.path.join(HERE, "fake_llama_server.py")]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class BuiltinTestCase(unittest.TestCase):
    def setUp(self):
        self.args_file = os.path.join(tempfile.mkdtemp(), "args.txt")
        self.env = {"FAKE_LLAMA_ARGS_FILE": self.args_file}
        for patcher in (
            mock.patch.object(builtin, "AI_BUILTIN_PORT", free_port()),
            mock.patch.object(builtin, "_launcher", side_effect=lambda variant: list(FAKE)),
            mock.patch.object(builtin, "_model_path", return_value="gemma.gguf"),
            mock.patch.object(builtin, "_variant", return_value="cuda"),
            mock.patch.object(builtin, "ENABLE_TOASTS", False),
            mock.patch.object(builtin.ui, "start_processing_spinner"),
            mock.patch.object(builtin.ui, "stop_processing_spinner"),
            mock.patch.dict(os.environ, self.env),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(builtin.stop)

    def launch_args(self):
        with open(self.args_file, encoding="utf-8") as f:
            return f.read().split("\n")


class TestStartingTheServer(BuiltinTestCase):
    def test_the_first_request_starts_the_server_and_gets_an_answer(self):
        self.assertEqual(builtin.ask("so um hello", None, "Polish this."), "Answer to: so um hello")

    def test_it_waits_while_the_model_loads(self):
        with mock.patch.dict(os.environ, {"FAKE_LLAMA_DELAY": "1.5"}):
            started = time.monotonic()
            self.assertEqual(builtin.ask("hello", None, "Polish."), "Answer to: hello")
        self.assertGreaterEqual(time.monotonic() - started, 1.4)

    def test_start_returns_only_once_the_server_answers(self):
        """Not as soon as the process exists: the model takes seconds to load."""
        with mock.patch.dict(os.environ, {"FAKE_LLAMA_DELAY": "1.5"}):
            self.assertTrue(builtin.start())
            self.assertTrue(builtin._healthy())

    def test_warm_up_starts_it_once(self):
        builtin.warm_up()
        first = builtin._process
        builtin.warm_up()
        builtin.ask("hello", None, "Polish.")
        self.assertIs(builtin._process, first)

    def test_it_runs_with_thinking_off_and_the_set_context(self):
        """Thinking on made Polish take 2.4-7.8 s instead of 0.26 s (measured)."""
        with mock.patch.object(builtin, "AI_NUM_CTX", 4096):
            builtin.warm_up()
        args = self.launch_args()
        self.assertIn("--reasoning", args, "thinking is not switched off")
        self.assertEqual(args[args.index("--reasoning") + 1], "off")
        self.assertEqual(args[args.index("-c") + 1], "4096")
        self.assertEqual(args[args.index("-ngl") + 1], "99")
        self.assertEqual(args[args.index("--host") + 1], "127.0.0.1")
        self.assertEqual(args[args.index("-m") + 1], "gemma.gguf")

    def test_the_cpu_build_keeps_the_model_off_the_graphics_card(self):
        with mock.patch.object(builtin, "_variant", return_value="cpu"):
            builtin.warm_up()
        args = self.launch_args()
        self.assertEqual(args[args.index("-ngl") + 1], "0")

    def test_the_server_is_tied_to_the_engine(self):
        """So it dies with the engine, even on a crash (the Job Object of phase 1)."""
        with mock.patch.object(builtin.signals, "bind_child_to_this_process") as bind:
            builtin.warm_up()
        bind.assert_called_once_with(builtin._process)


class TestSharing(BuiltinTestCase):
    def test_a_server_already_running_is_used_not_started_again(self):
        """The reader is a separate process: it uses the engine's server, so the model
        is never loaded twice."""
        builtin.warm_up()
        owner = builtin._process
        with mock.patch.object(builtin, "_process", None), \
             mock.patch.object(builtin.subprocess, "Popen") as popen:
            self.assertEqual(builtin.ask("hi", None, "Polish."), "Answer to: hi")
        popen.assert_not_called()
        self.assertIsNotNone(owner.poll() is None)


class TestFailures(BuiltinTestCase):
    def test_a_crashed_server_is_restarted_once(self):
        with mock.patch.dict(os.environ, {"FAKE_LLAMA_CRASH_AFTER": "1"}):
            self.assertEqual(builtin.ask("one", None, "Polish."), "Answer to: one")
            builtin._process.wait(5)                      # it exits after that answer
            with self.assertLogs(level="WARNING") as logs:
                self.assertEqual(builtin.ask("two", None, "Polish."), "Answer to: two")
        self.assertIn("restart", "\n".join(logs.output).lower())

    def test_a_missing_runtime_gives_no_answer_and_says_why(self):
        builtin._launcher.side_effect = builtin.BuiltinUnavailable("not installed")
        with self.assertLogs(level="WARNING") as logs:
            self.assertIsNone(builtin.ask("hello", None, "Polish."))
        self.assertIn("not installed", "\n".join(logs.output))

    def test_a_server_that_never_gets_ready_gives_no_answer(self):
        with mock.patch.object(builtin, "START_TIMEOUT", 1), \
             mock.patch.dict(os.environ, {"FAKE_LLAMA_DELAY": "10"}), \
             self.assertLogs(level="WARNING"):
            self.assertIsNone(builtin.ask("hello", None, "Polish."))


class TestChoosingTheBuiltinProvider(unittest.TestCase):
    def test_it_is_chosen_when_its_runtime_is_installed(self):
        with mock.patch.object(builtin, "available", return_value=True):
            self.assertIs(llm.choose("builtin"), builtin)

    def test_without_its_runtime_ollama_is_used_and_the_fix_named(self):
        with mock.patch.object(builtin, "available", return_value=False), \
             mock.patch.object(llm.settings, "problems", []):
            self.assertIs(llm.choose("builtin"), llm.ollama)
            self.assertEqual(len(llm.settings.problems), 1)
            self.assertIn("get_llama.py", llm.settings.problems[0])

    def test_available_means_the_runtime_for_this_pc_is_installed(self):
        with mock.patch.object(builtin, "_variant", return_value="vulkan"), \
             mock.patch.object(rt, "installed", side_effect=lambda v: v == "cuda"):
            self.assertFalse(builtin.available())


class TestNamingTheModel(unittest.TestCase):
    """The banner and the first-run download name the model actually configured."""

    def test_the_default_model_is_named_e4b(self):
        with mock.patch.object(builtin, "_variant", return_value="cuda"):
            self.assertEqual(builtin.model_name(), "Gemma 4 E4B · built in (cuda)")

    def test_the_smaller_model_is_named_e2b(self):
        with mock.patch.object(builtin, "AI_BUILTIN_FILE", "gemma-4-E2B_q4_0-it.gguf"), \
             mock.patch.object(builtin, "_variant", return_value="cpu"):
            self.assertEqual(builtin.model_name(), "Gemma 4 E2B · built in (cpu)")

    def test_another_model_is_named_by_its_file(self):
        with mock.patch.object(builtin, "AI_BUILTIN_FILE", "Qwen3-4B-Q4_K_M.gguf"), \
             mock.patch.object(builtin, "_variant", return_value="cuda"):
            self.assertEqual(builtin.model_name(), "Qwen3-4B-Q4_K_M · built in (cuda)")


if __name__ == "__main__":
    unittest.main()
