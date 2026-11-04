"""The dictation half's cases a user meets: Shift+F2, a microphone that will not open,
a clip too short or cancelled, the five-minute limit, a failure while processing,
Unload AI, the keys it binds, and starting it alone. No microphone is opened, no key
is bound, nothing is typed."""
import logging
import os
import sys
import tempfile
import threading
import unittest
from logging.handlers import RotatingFileHandler
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import engine, hotkeys
from zeroflow.capture import Capture


class EngineTestCase(unittest.TestCase):
    def setUp(self):
        for patcher in (mock.patch.object(engine, "ENABLE_AUDIO_CHIMES", False),
                        mock.patch.object(engine, "ENABLE_TOASTS", False),
                        mock.patch.object(engine, "current_capture", None),
                        mock.patch.object(engine.ui, "update_console_title"),
                        mock.patch.object(engine.ui, "play_tone"),
                        mock.patch.object(engine.ui, "set_tray_state"),
                        mock.patch.object(engine.signals, "set_recording"),
                        mock.patch("sys.stdout")):
            patcher.start()
            self.addCleanup(patcher.stop)


class TestClearLogsAndHistory(EngineTestCase):
    """Shift+F2."""

    def setUp(self):
        super().setUp()
        folder = tempfile.mkdtemp(prefix="zeroflow-purge-test-")
        self.addCleanup(lambda: __import__("shutil").rmtree(folder, ignore_errors=True))
        self.history = os.path.join(folder, "flow_history.md")
        self.log = os.path.join(folder, "flow_debug.log")
        with open(self.history, "w", encoding="utf-8") as f:
            f.write("[12:00:00] [EN_RAW]\nprivate words\n")
        for suffix in (".1", ".2"):
            with open(self.log + suffix, "w", encoding="utf-8") as f:
                f.write("old")
        self.handler = RotatingFileHandler(self.log, encoding="utf-8")
        self.handler.stream.write("old lines\n")
        self.handler.flush()
        self.addCleanup(self.handler.close)
        for patcher in (mock.patch.object(engine, "HISTORY_FILE", self.history),
                        mock.patch.object(engine, "LOG_FILE", self.log),
                        mock.patch.object(engine, "LOG_HANDLER", self.handler)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_history_log_and_backups_are_cleared(self):
        engine.purge_diagnostic_files()
        self.handler.flush()
        self.assertEqual(os.path.getsize(self.history), 0)
        with open(self.log, encoding="utf-8") as f:
            self.assertNotIn("old lines", f.read())
        self.assertFalse(os.path.exists(self.log + ".1") or os.path.exists(self.log + ".2"))

    def test_nothing_is_cleared_while_recording(self):
        with mock.patch.object(engine, "current_capture", Capture("en_raw")):
            engine.purge_diagnostic_files()
        self.assertGreater(os.path.getsize(self.history), 0)

    def test_the_log_stays_usable_afterwards(self):
        """A handler lock left held would freeze every later log line."""
        engine.purge_diagnostic_files()
        self.assertTrue(self.handler.lock.acquire(timeout=1))
        self.handler.lock.release()


class FakeMic:
    """sd.InputStream stand-in: hands the capture `seconds` of audio, then — like a
    second press of the record key, or Esc with `cancel` — stops it, unless
    `stop_after` is False."""

    def __init__(self, seconds, fail=None, stop_after=True, cancel=False):
        self.seconds, self.fail, self.stop_after, self.cancel = seconds, fail, stop_after, cancel

    def __call__(self, **kwargs):
        if self.fail:
            raise self.fail
        self.callback = kwargs["callback"]
        return self

    def __enter__(self):
        if self.seconds:
            self.callback(np.full((int(self.seconds * 16000), 1), 0.1, np.float32), 0, None, None)
        if self.stop_after:
            self.callback.__self__.stop(cancel=self.cancel)   # the Capture it feeds
        return self

    def __exit__(self, *exc):
        return False


class TestOneRecording(EngineTestCase):
    def record(self, mic):
        capture = Capture("en_raw")
        engine.current_capture = capture
        with mock.patch.object(engine.sd, "InputStream", mic), \
             mock.patch.object(engine, "transcribe_and_inject") as transcribe:
            engine.process_recording(capture)
        return capture, transcribe

    def test_a_microphone_that_will_not_open_says_so_and_frees_the_reader(self):
        with self.assertLogs(level="ERROR") as logs:
            capture, transcribe = self.record(FakeMic(0, fail=OSError("no device")))
        self.assertTrue(capture.cancelled)
        transcribe.assert_not_called()
        self.assertIn("no device", "\n".join(logs.output))
        engine.signals.set_recording.assert_called_with(False)
        self.assertIsNone(engine.current_capture)

    def test_a_clip_shorter_than_the_minimum_is_dropped(self):
        _, transcribe = self.record(FakeMic(0.2))
        transcribe.assert_not_called()

    def test_a_cancelled_clip_is_never_transcribed(self):
        _, transcribe = self.record(FakeMic(2.0, cancel=True))
        transcribe.assert_not_called()

    def test_a_normal_clip_is_transcribed(self):
        _, transcribe = self.record(FakeMic(2.0))
        transcribe.assert_called_once()
        self.assertEqual(len(transcribe.call_args.args[0]), 32000)

    def test_a_forgotten_recording_stops_by_itself_and_is_kept(self):
        with mock.patch.object(engine, "MAX_RECORDING_SECONDS", 0.05), \
             self.assertLogs(level="INFO") as logs:
            capture, transcribe = self.record(FakeMic(1.0, stop_after=False))
        self.assertTrue(capture.stopped.is_set())
        self.assertFalse(capture.cancelled)
        transcribe.assert_called_once()
        self.assertIn("stopped by itself", "\n".join(logs.output))

    def test_a_failure_while_processing_is_logged_and_the_title_reset(self):
        capture = Capture("en_raw")
        engine.current_capture = capture
        with mock.patch.object(engine.sd, "InputStream", FakeMic(2.0)), \
             mock.patch.object(engine, "transcribe_and_inject", side_effect=RuntimeError("bad")), \
             self.assertLogs(level="ERROR") as logs:
            engine.process_recording(capture)
        self.assertIn("bad", "\n".join(logs.output))
        engine.ui.update_console_title.assert_called_with("ONLINE")
        self.assertFalse(engine.processing_lock.locked())


class TestUnloadAI(EngineTestCase):
    def test_each_tray_request_unloads_once(self):
        with mock.patch.object(engine.signals, "wait_for_ai_unload", side_effect=[True, True, False]), \
             mock.patch.object(engine, "unload_ai", return_value=True) as unload:
            engine.watch_for_unload_requests()
        self.assertEqual(unload.call_count, 2)

    def test_it_says_when_there_was_nothing_to_unload(self):
        with mock.patch.object(engine, "unload_ai", return_value=False), \
             mock.patch("builtins.print") as shown:
            engine.unload_ai_model()
        self.assertIn("nothing to unload", shown.call_args.args[0])


class TestKeysAndStart(EngineTestCase):
    def test_every_key_is_bound_and_only_esc_reaches_the_app(self):
        with mock.patch.object(engine.keyboard, "add_hotkey") as bind:
            engine.register_hotkeys()
        bound = {call.args[0]: call.kwargs.get("suppress", False) for call in bind.call_args_list}
        self.assertEqual(set(bound), set(engine.HOTKEYS.values()))
        self.assertFalse(bound[engine.HOTKEYS["panic"]])
        self.assertTrue(all(suppress for key, suppress in bound.items()
                            if key != engine.HOTKEYS["panic"]))

    def test_a_second_dictation_half_stops_at_the_door(self):
        with mock.patch.object(engine.signals, "claim_single_instance", return_value=False), \
             mock.patch.object(engine.ui, "already_running") as told, \
             mock.patch.object(engine, "boot") as boot:
            engine.main()
        told.assert_called_once()
        boot.assert_not_called()

    def test_a_crash_alone_exits_with_an_error_code(self):
        with mock.patch.object(engine, "main", side_effect=RuntimeError("boom")), \
             mock.patch.object(engine.ui, "alert"), \
             self.assertLogs(level="CRITICAL"):
            self.assertEqual(engine.run(), 1)
        with mock.patch.object(engine, "main"):
            self.assertEqual(engine.run(), 0)


class TestActionKeysRunApart(unittest.TestCase):
    def test_a_failing_action_is_logged_and_the_keyboard_is_never_blocked(self):
        done = threading.Event()

        def broken():
            done.set()
            raise ValueError("bad action")
        with mock.patch.object(hotkeys.ui, "update_console_title"), \
             mock.patch("sys.stdout"), \
             self.assertLogs(level="ERROR") as logs:
            hotkeys.run_async(broken)()                   # returns at once
            self.assertTrue(done.wait(2))
            for _ in range(50):
                if logs.output:
                    break
                threading.Event().wait(0.02)
        self.assertIn("bad action", "\n".join(logs.output))


if __name__ == "__main__":
    logging.basicConfig()
    unittest.main()
