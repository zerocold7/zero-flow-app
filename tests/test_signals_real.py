"""The signals between the two halves, on real Windows events and mutexes.

Each test uses names of its own, so the engine you may have running is never muted,
silenced or told to exit. Without signalling (no kernel32), every helper must mean
"nothing is happening" rather than fail.
"""
import os
import sys
import threading
import time
import unittest
import uuid
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import signals


class RealSignalsTestCase(unittest.TestCase):
    def setUp(self):
        tag = uuid.uuid4().hex[:8]
        for patcher in (
                mock.patch.object(signals, "_RECORDING_NAME", f"Local\\ZeroFlowTest.{tag}.rec"),
                mock.patch.object(signals, "_SILENCE_NAME", f"Local\\ZeroFlowTest.{tag}.silence"),
                mock.patch.object(signals, "_EXIT_NAME", f"Local\\ZeroFlowTest.{tag}.exit"),
                mock.patch.object(signals, "_UNLOAD_AI_NAME", f"Local\\ZeroFlowTest.{tag}.unload"),
                mock.patch.object(signals, "_CLIPBOARD_MUTEX_NAME", f"Local\\ZeroFlowTest.{tag}.clip"),
                mock.patch.object(signals, "_clipboard_handle", None),
                mock.patch.object(signals, "_clipboard_fallback", None),
                mock.patch.dict(signals._handles, clear=True)):
            patcher.start()
            self.addCleanup(patcher.stop)


class TestTheMicrophoneFlag(RealSignalsTestCase):
    def test_the_reader_sees_the_mic_open_and_closed(self):
        self.assertFalse(signals.is_recording())
        signals.set_recording(True)
        self.assertTrue(signals.is_recording())
        self.assertTrue(signals.is_recording())          # stays set while recording
        signals.set_recording(False)
        self.assertFalse(signals.is_recording())


class TestSilenceRequest(RealSignalsTestCase):
    def test_a_waiting_reader_is_woken_once(self):
        woken = []
        waiter = threading.Thread(target=lambda: woken.append(signals.wait_for_silence_request(3000)))
        waiter.start()
        time.sleep(0.1)
        signals.request_reader_silence()
        waiter.join(3)
        self.assertEqual(woken, [True])
        self.assertFalse(signals.wait_for_silence_request(0))   # a pulse, not a state


class TestExitAndUnload(RealSignalsTestCase):
    def test_exit_once_asked_stays_asked(self):
        self.assertFalse(signals.exit_requested())
        signals.request_exit()
        self.assertTrue(signals.exit_requested())
        self.assertTrue(signals.wait_for_exit(0))

    def test_an_unload_request_is_answered_once(self):
        self.assertFalse(signals.wait_for_ai_unload(0))
        signals.request_ai_unload()
        self.assertTrue(signals.wait_for_ai_unload(0))
        self.assertFalse(signals.wait_for_ai_unload(0))


class TestClipboardLock(RealSignalsTestCase):
    def test_one_holder_at_a_time(self):
        inside, events = threading.Event(), []

        def other():
            with signals.clipboard_lock():
                events.append("other in")

        with signals.clipboard_lock():
            events.append("first in")
            thread = threading.Thread(target=other)
            thread.start()
            time.sleep(0.2)
            events.append("first out")
            inside.set()
        thread.join(3)
        self.assertEqual(events, ["first in", "first out", "other in"])

    def test_nested_use_on_one_thread_does_not_deadlock(self):
        with signals.clipboard_lock():
            with signals.clipboard_lock():
                pass


class TestWithoutSignalling(unittest.TestCase):
    """Not Windows, or kernel32 unusable: each half behaves as if alone."""

    def setUp(self):
        for patcher in (mock.patch.object(signals, "_kernel32", None),
                        mock.patch.object(signals, "_clipboard_handle", None),
                        mock.patch.object(signals, "_clipboard_fallback", None),
                        mock.patch.dict(signals._handles, clear=True),
                        mock.patch.dict(signals._instance_handles, clear=True)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_nothing_is_happening_and_nothing_fails(self):
        self.assertFalse(signals.available())
        signals.set_recording(True)
        signals.request_reader_silence()
        signals.request_exit()
        signals.request_ai_unload()
        self.assertFalse(signals.is_recording())
        self.assertFalse(signals.wait_for_silence_request(0))
        self.assertFalse(signals.exit_requested())
        self.assertFalse(signals.wait_for_ai_unload(0))
        self.assertTrue(signals.claim_single_instance("dictation"))

    def test_the_clipboard_lock_falls_back_to_an_in_process_lock(self):
        with signals.clipboard_lock():
            pass
        self.assertIsNotNone(signals._clipboard_fallback)


if __name__ == "__main__":
    unittest.main()
