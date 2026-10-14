"""Recording: start, stop, cancel and the next recording, pressed in quick succession.

Every capture used to share one audio queue, one "recording" flag and one "cancel"
flag. Pressed quickly, one recording could keep another's audio, lose its own, be
transcribed after Esc, or be stopped by an earlier recording's microphone error.

The microphone is a fake: each test feeds it audio and decides when it opens, so the
exact timing that broke the old code is reproduced every run. Transcription is
replaced by a recorder of what would have been transcribed.
"""
import contextlib
import io
import os
import sys
import threading
import time
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import local_flow

RATE = local_flow.SAMPLE_RATE
HALF_SECOND = RATE // 2                       # longer than MIN_CLIP_SECONDS


def wait_until(condition, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.005)
    return condition()


class FakeMicrophone:
    """Stands in for sounddevice.InputStream. Each stream opened is kept, so a test
    can feed it audio through the callback the engine registered."""

    def __init__(self):
        self.streams = []
        self.before_open = {}                 # stream number -> function run on open

    def InputStream(self, callback, **kwargs):
        mic = self
        number = len(self.streams)

        class Stream:
            def __init__(self):
                self.callback = callback
                self.open = False

            def __enter__(self):
                hook = mic.before_open.get(number)
                if hook:
                    hook()                    # may block, or raise like a missing mic
                self.open = True
                return self

            def __exit__(self, *exc):
                self.open = False
                return False

        stream = Stream()
        self.streams.append(stream)
        return stream

    def feed(self, number, value, frames=HALF_SECOND):
        stream = self.streams[number]
        stream.callback(np.full((frames, 1), value, dtype=np.float32), frames, None, None)


class CaptureTestCase(unittest.TestCase):
    def setUp(self):
        self.mic = FakeMicrophone()
        self.transcribed = []                 # (mode, audio) for every clip processed
        self.recording_signal = []            # what the reader was told, in order
        self.done = threading.Event()

        def transcribe(audio, mode, context):
            self.transcribed.append((mode, audio.copy()))

        fake_sd = mock.Mock(InputStream=self.mic.InputStream, sleep=lambda ms: time.sleep(ms / 1000))
        patches = [
            mock.patch.object(local_flow, "sd", fake_sd),
            mock.patch.object(local_flow, "transcribe_and_inject", side_effect=transcribe),
            mock.patch.object(local_flow, "ENABLE_AUDIO_CHIMES", False),
            # A recording a broken test leaves behind ends on its own, rather than
            # holding the test run open for the real five-minute limit.
            mock.patch.object(local_flow, "MAX_RECORDING_SECONDS", 3),
            mock.patch.object(local_flow.ui, "set_tray_state"),
            mock.patch.object(local_flow.ui, "update_console_title"),
            mock.patch.object(local_flow.ui, "play_tone"),
            mock.patch.object(local_flow.signals, "request_reader_silence"),
            mock.patch.object(local_flow.signals, "set_recording",
                              side_effect=self.recording_signal.append),
            contextlib.redirect_stdout(io.StringIO()),
        ]
        for patcher in patches:
            patcher.__enter__()
            self.addCleanup(patcher.__exit__, None, None, None)
        # A test that fails mid-recording must not leave a capture running for the next.
        self.addCleanup(self.stop_everything)

    def stop_everything(self):
        if local_flow.is_recording():
            local_flow.on_cancel_hotkey()
        time.sleep(0.1)

    def press(self, mode):
        local_flow.on_record_hotkey(mode)

    def wait_for_streams(self, count):
        self.assertTrue(wait_until(lambda: len(self.mic.streams) >= count
                                   and self.mic.streams[count - 1].open),
                        f"stream {count} never opened")

    def wait_for_clips(self, count):
        wait_until(lambda: len(self.transcribed) >= count)
        time.sleep(0.1)                       # and nothing more arrives after it


class TestBackToBack(CaptureTestCase):
    def test_stop_then_start_keeps_the_two_clips_apart(self):
        """F5 to stop, F7 straight after to start the next: each clip holds only its
        own audio. The old shared flag made the first recording carry on, and the
        shared queue let the second wipe the first."""
        self.press("en_raw")
        self.wait_for_streams(1)
        self.mic.feed(0, 0.1)
        self.press("en_raw")                  # stop
        self.press("ar_raw")                  # and start the next at once
        self.wait_for_streams(2)
        self.mic.feed(1, 0.2)
        self.press("ar_raw")                  # stop
        self.wait_for_clips(2)

        self.assertEqual([mode for mode, _ in self.transcribed], ["en_raw", "ar_raw"])
        first, second = (audio for _, audio in self.transcribed)
        self.assertTrue(np.all(first == np.float32(0.1)) and len(first) == HALF_SECOND)
        self.assertTrue(np.all(second == np.float32(0.2)) and len(second) == HALF_SECOND)


class TestCancel(CaptureTestCase):
    def test_a_cancelled_clip_stays_cancelled_when_the_next_starts(self):
        """Esc, then a record key at once: the old shared "cancel" flag was reset by
        the new recording, so the cancelled clip was transcribed and pasted."""
        self.press("en_raw")
        self.wait_for_streams(1)
        self.mic.feed(0, 0.1)
        local_flow.on_cancel_hotkey()
        self.press("ar_raw")
        self.wait_for_streams(2)
        self.mic.feed(1, 0.2)
        self.press("ar_raw")
        self.wait_for_clips(1)

        self.assertEqual([mode for mode, _ in self.transcribed], ["ar_raw"])

    def test_cancel_when_idle_does_nothing(self):
        local_flow.on_cancel_hotkey()
        self.assertFalse(local_flow.is_recording())


class TestMicrophoneError(CaptureTestCase):
    def test_a_failed_microphone_does_not_stop_the_next_recording(self):
        """The first recording's mic is slow to open and then fails, after the user
        has already stopped it and started another. Its error path switched the
        shared flag off — stopping the new recording — and told the reader the mic
        was closed while it was open."""
        second_started = threading.Event()

        def slow_then_broken():
            second_started.wait(2)
            raise OSError("no input device")

        self.mic.before_open[0] = slow_then_broken
        self.mic.before_open[1] = second_started.set
        self.press("en_raw")
        self.assertTrue(wait_until(lambda: len(self.mic.streams) == 1))
        self.press("en_raw")                  # stop the one still opening
        self.press("ar_raw")
        self.wait_for_streams(2)
        time.sleep(0.15)                      # the first one's failure has run by now

        self.assertTrue(local_flow.is_recording())
        self.assertIs(self.recording_signal[-1], True, "the reader was told the mic closed")
        self.mic.feed(1, 0.2)
        self.press("ar_raw")
        self.wait_for_clips(1)
        self.assertEqual([mode for mode, _ in self.transcribed], ["ar_raw"])


class TestMaximumLength(CaptureTestCase):
    def test_a_forgotten_recording_stops_by_itself(self):
        """A recording left running grew by ~4 MB a minute until someone noticed.
        It now stops at MAX_RECORDING_SECONDS and is transcribed as usual."""
        with mock.patch.object(local_flow, "MAX_RECORDING_SECONDS", 0.3, create=True):
            self.press("en_raw")
            self.wait_for_streams(1)
            self.mic.feed(0, 0.1)
            self.wait_for_clips(1)
        self.assertEqual([mode for mode, _ in self.transcribed], ["en_raw"])
        self.assertFalse(local_flow.is_recording())
        self.assertIs(self.recording_signal[-1], False)


if __name__ == "__main__":
    unittest.main()
