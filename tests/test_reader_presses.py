"""Two quick F4 presses start one read, not two.

Each press runs on its own thread. The reader checked a plain "busy" flag and set it
a few steps later, so a second press landing in between also passed the check: two
selection copies fought over the clipboard and two reads were queued. The test holds
the first press inside that gap (in signals.is_recording, which runs between the two)
and sends the second press through it.
"""
import os
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reader import app


class TestTwoPresses(unittest.TestCase):
    def test_a_press_during_a_read_starts_no_second_one(self):
        in_gap, let_go = threading.Event(), threading.Event()
        presses = []

        def is_recording():
            presses.append(threading.current_thread().name)
            if len(presses) == 1:                # hold the first press in the gap
                in_gap.set()
                let_go.wait(5)
            return False
        with mock.patch.object(app.signals, "is_recording", side_effect=is_recording), \
             mock.patch.object(app.voice_engine, "interrupt_audio"), \
             mock.patch.object(app.voice_engine, "stream_audio") as speak, \
             mock.patch.object(app.keyboard, "release"), \
             mock.patch.object(app, "copy_selection", return_value="read this"), \
             mock.patch.object(app, "clean_text_instant", side_effect=lambda t: t), \
             mock.patch.object(app, "use_smart_mode", False), \
             mock.patch.object(app, "is_suspended", False), \
             mock.patch.object(app, "_title"), \
             mock.patch.object(app.ui, "play_tone"), \
             mock.patch("sys.stdout"):
            first = threading.Thread(target=app.process_and_speak, name="first")
            first.start()
            self.assertTrue(in_gap.wait(5))
            second = threading.Thread(target=app.process_and_speak, name="second")
            second.start()
            second.join(5)
            let_go.set()
            first.join(5)
        self.assertEqual(speak.call_count, 1)

    def test_the_next_press_after_a_read_works(self):
        with mock.patch.object(app.signals, "is_recording", return_value=False), \
             mock.patch.object(app.voice_engine, "interrupt_audio"), \
             mock.patch.object(app.voice_engine, "stream_audio") as speak, \
             mock.patch.object(app.keyboard, "release"), \
             mock.patch.object(app, "copy_selection", return_value="read this"), \
             mock.patch.object(app, "clean_text_instant", side_effect=lambda t: t), \
             mock.patch.object(app, "use_smart_mode", False), \
             mock.patch.object(app, "is_suspended", False), \
             mock.patch.object(app, "_title"), \
             mock.patch.object(app.ui, "play_tone"), \
             mock.patch("sys.stdout"):
            app.process_and_speak()
            app.process_and_speak()
        self.assertEqual(speak.call_count, 2)

    def test_a_failed_read_does_not_lock_the_key(self):
        with mock.patch.object(app.signals, "is_recording", return_value=False), \
             mock.patch.object(app.voice_engine, "interrupt_audio"), \
             mock.patch.object(app.voice_engine, "stream_audio",
                               side_effect=[RuntimeError("no voice"), None]) as speak, \
             mock.patch.object(app.keyboard, "release"), \
             mock.patch.object(app, "copy_selection", return_value="read this"), \
             mock.patch.object(app, "clean_text_instant", side_effect=lambda t: t), \
             mock.patch.object(app, "use_smart_mode", False), \
             mock.patch.object(app, "is_suspended", False), \
             mock.patch.object(app, "_title"), \
             mock.patch.object(app.ui, "play_tone"), \
             mock.patch.object(app.traceback, "print_exc"), \
             mock.patch("sys.stdout"), \
             self.assertLogs(level="ERROR"):
            app.process_and_speak()
            app.process_and_speak()
        self.assertEqual(speak.call_count, 2)


if __name__ == "__main__":
    unittest.main()
