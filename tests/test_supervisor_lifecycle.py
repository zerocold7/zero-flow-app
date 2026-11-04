"""The whole engine's life: starting the reader, the tray's Exit, shutting down, a
crash, and a second copy. No real process is started, no key bound, nothing exits."""
import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import supervisor


class SupervisorTestCase(unittest.TestCase):
    def setUp(self):
        for patcher in (mock.patch.object(supervisor, "shutting_down", False),
                        mock.patch.object(supervisor, "reader_process", None),
                        mock.patch("sys.stdout")):
            patcher.start()
            self.addCleanup(patcher.stop)


class TestStartingTheReader(SupervisorTestCase):
    def test_the_reader_is_a_child_sharing_this_console_and_dies_with_it(self):
        child = mock.Mock()
        with mock.patch.object(supervisor.subprocess, "Popen", return_value=child) as popen, \
             mock.patch.object(supervisor.signals, "bind_child_to_this_process") as bind:
            self.assertIs(supervisor.spawn_reader(), child)
        args, kwargs = popen.call_args
        self.assertEqual(args[0][1:], ["-m", "reader"])
        self.assertEqual(kwargs["env"]["ZEROFLOW_CHILD"], "1")
        self.assertNotIn("creationflags", kwargs)        # shares the console window
        bind.assert_called_once_with(child)

    def test_a_reader_that_cannot_start_leaves_dictation_running(self):
        with mock.patch.object(supervisor.subprocess, "Popen", side_effect=OSError("no python")), \
             self.assertLogs(level="ERROR") as logs:
            self.assertIsNone(supervisor.spawn_reader())
        self.assertIn("no python", "\n".join(logs.output))


class TestExitFromTheTray(SupervisorTestCase):
    def test_the_exit_signal_shuts_the_engine_down(self):
        with mock.patch.object(supervisor.signals, "available", return_value=True), \
             mock.patch.object(supervisor.signals, "wait_for_exit", return_value=True), \
             mock.patch.object(supervisor, "shutdown") as shutdown:
            supervisor.watch_for_exit()
        shutdown.assert_called_once_with()

    def test_without_signalling_the_watcher_just_ends(self):
        with mock.patch.object(supervisor.signals, "available", return_value=False), \
             mock.patch.object(supervisor.signals, "wait_for_exit") as wait, \
             mock.patch.object(supervisor, "shutdown") as shutdown:
            supervisor.watch_for_exit()
        wait.assert_not_called()
        shutdown.assert_not_called()


class TestShutdown(SupervisorTestCase):
    def test_the_reader_is_stopped_then_the_process_exits_with_the_code(self):
        reader = mock.Mock()
        reader.poll.return_value = None
        with mock.patch.object(supervisor, "reader_process", reader), \
             mock.patch.object(supervisor.os, "_exit") as exit_:
            supervisor.shutdown(1)
        reader.terminate.assert_called_once()
        reader.wait.assert_called_once_with(timeout=5)
        reader.kill.assert_not_called()
        exit_.assert_called_once_with(1)
        self.assertTrue(supervisor.shutting_down)       # so watch_reader does not restart it

    def test_a_reader_that_does_not_stop_is_killed(self):
        reader = mock.Mock()
        reader.poll.return_value = None
        reader.wait.side_effect = subprocess.TimeoutExpired("reader", 5)
        with mock.patch.object(supervisor, "reader_process", reader), \
             mock.patch.object(supervisor.os, "_exit"):
            supervisor.shutdown()
        reader.kill.assert_called_once()


class TestRun(SupervisorTestCase):
    def test_ctrl_c_is_a_clean_stop(self):
        with mock.patch.object(supervisor, "main", side_effect=KeyboardInterrupt), \
             mock.patch.object(supervisor, "shutdown") as shutdown:
            supervisor.run()
        shutdown.assert_called_once_with()

    def test_a_crash_is_reported_and_exits_with_an_error_code(self):
        with mock.patch.object(supervisor, "main", side_effect=RuntimeError("boom")), \
             mock.patch.object(supervisor.engine, "report_fatal_error") as report, \
             mock.patch.object(supervisor, "shutdown") as shutdown:
            supervisor.run()
        report.assert_called_once_with("engine")
        shutdown.assert_called_once_with(1)


class TestMain(SupervisorTestCase):
    def test_a_second_engine_stops_at_the_door(self):
        with mock.patch.object(supervisor.signals, "claim_single_instance", return_value=False), \
             mock.patch.object(supervisor.ui, "already_running") as told, \
             mock.patch.object(supervisor.engine, "boot") as boot:
            supervisor.main()
        told.assert_called_once()
        boot.assert_not_called()

    def test_whisper_loads_before_the_reader_starts_and_keys_come_last(self):
        order = []
        with mock.patch.object(supervisor.signals, "claim_single_instance", return_value=True), \
             mock.patch.object(supervisor.engine, "boot", side_effect=lambda: order.append("boot")), \
             mock.patch.object(supervisor, "show_banner"), \
             mock.patch.object(supervisor.ui, "set_window_icon"), \
             mock.patch.object(supervisor.ui, "show_toast"), \
             mock.patch.object(supervisor, "spawn_reader",
                               side_effect=lambda: order.append("reader")), \
             mock.patch.object(supervisor.threading, "Thread"), \
             mock.patch.object(supervisor.engine, "register_hotkeys",
                               side_effect=lambda: order.append("keys")), \
             mock.patch.object(supervisor.keyboard, "wait", side_effect=lambda: order.append("wait")):
            supervisor.main()
        self.assertEqual(order, ["boot", "reader", "keys", "wait"])


if __name__ == "__main__":
    unittest.main()
