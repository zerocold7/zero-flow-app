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
    def test_the_reader_is_a_child_process_that_dies_with_the_engine(self):
        child = mock.Mock()
        with mock.patch.object(supervisor.subprocess, "Popen", return_value=child) as popen, \
             mock.patch.object(supervisor.signals, "bind_child_to_this_process") as bind:
            self.assertIs(supervisor.spawn_reader(), child)
        args, kwargs = popen.call_args
        self.assertEqual(args[0][1:], ["-m", "reader"])
        self.assertNotIn("creationflags", kwargs)        # shares a console if there is one
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

    def test_a_restarted_engine_waits_for_the_old_one_a_fresh_start_does_not(self):
        for argv, wait in (([supervisor.RESTART_FLAG], supervisor.RESTART_WAIT), ([], 0)):
            with mock.patch.object(supervisor.sys, "argv", ["zero_flow.py", *argv]),                  mock.patch.object(supervisor.signals, "claim_single_instance",
                                   return_value=False) as claim,                  mock.patch.object(supervisor.ui, "already_running"):
                supervisor.main()
            self.assertEqual(claim.call_args_list[0].args, ("dictation", wait))


class TestTheHalves(SupervisorTestCase):
    def test_dictation_loads_the_models_before_it_binds_the_keys(self):
        order = []
        with mock.patch.object(supervisor.engine, "load_models",
                               side_effect=lambda: order.append("models")),              mock.patch.object(supervisor.engine, "register_hotkeys",
                               side_effect=lambda: order.append("keys")):
            half = supervisor.DictationHalf()
            half.start()
        self.assertEqual(order, ["models", "keys"])
        self.assertTrue(half.running)

    def test_dictation_off_lets_go_of_the_keys_then_frees_the_models(self):
        order = []
        with mock.patch.object(supervisor.engine, "unregister_hotkeys",
                               side_effect=lambda: order.append("keys")),              mock.patch.object(supervisor.engine, "free_models",
                               side_effect=lambda: order.append("models")):
            half = supervisor.DictationHalf()
            half.running = True
            half.stop()
        self.assertEqual(order, ["keys", "models"])
        self.assertFalse(half.running)

    def test_the_reader_off_ends_its_process_and_is_not_restarted(self):
        child = mock.Mock()
        child.poll.return_value = None
        with mock.patch.object(supervisor, "reader_process", child),              mock.patch.object(supervisor, "reader_wanted", True):
            supervisor.ReaderHalf().stop()
            self.assertFalse(supervisor.reader_wanted)
        child.terminate.assert_called_once()

    def test_the_reader_on_starts_a_child_and_watches_it(self):
        child = mock.Mock()
        with mock.patch.object(supervisor, "spawn_reader", return_value=child),              mock.patch.object(supervisor.threading, "Thread") as thread,              mock.patch.object(supervisor, "reader_process", None):
            supervisor.ReaderHalf().start()
            self.assertIs(supervisor.reader_process, child)
        thread.assert_called_once()


class TestRestart(SupervisorTestCase):
    def test_saving_starts_a_new_engine_with_the_flag_then_ends_this_one(self):
        with mock.patch.object(supervisor.subprocess, "Popen") as popen,              mock.patch.object(supervisor, "shutdown") as shutdown:
            supervisor.restart()
        command = popen.call_args.args[0]
        self.assertTrue(command[1].endswith("zero_flow.py"))
        self.assertEqual(command[2], supervisor.RESTART_FLAG)
        shutdown.assert_called_once_with()

    def test_if_the_new_engine_cannot_start_this_one_stays(self):
        with mock.patch.object(supervisor.subprocess, "Popen", side_effect=OSError("no")),              mock.patch.object(supervisor, "shutdown") as shutdown,              self.assertLogs(level="ERROR"):
            supervisor.restart()
        shutdown.assert_not_called()


if __name__ == "__main__":
    unittest.main()
