"""Reader playback — who is allowed to touch sounddevice.

sd.play / sd.wait / sd.stop share one module-global stream and are not thread-safe.
When interrupt_audio() called sd.stop() from the Esc hotkey while the playback worker
sat in sd.wait(), both threads closed the same PortAudio stream, and the reader died
with 0xC0000005 / 0xC0000374. These tests swap in a fake sounddevice that records
which thread calls it, so they need no audio device and make no sound.
"""
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reader import voice_engine


class FakeStream:
    def __init__(self, sd, active):
        self._sd = sd
        self.active = active

    def abort(self):
        self._sd.record("abort")
        self.active = False


class FakeSoundDevice:
    """Streams stay active until aborted, like a long chunk still playing — unless
    `finish_instantly` is set, which plays each chunk in zero time."""

    def __init__(self, finish_instantly=False):
        self.calls = []
        self.played = []
        self.finish_instantly = finish_instantly
        self._stream = None

    def record(self, name):
        self.calls.append((name, threading.get_ident()))

    def play(self, audio, samplerate):
        self.record("play")
        self.played.append(audio)
        self._stream = FakeStream(self, active=not self.finish_instantly)

    def get_stream(self):
        return self._stream

    def stop(self):
        self.record("stop")


def wait_until(condition, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.005)
    return False


class PlaybackTestCase(unittest.TestCase):
    def install(self, fake):
        self._real_sd = voice_engine.sd
        voice_engine.sd = fake                   # the worker looks `sd` up on every call
        self.addCleanup(self.restore)

    def restore(self):
        voice_engine.interrupt_audio()           # leave nothing queued for the next test
        time.sleep(0.05)
        voice_engine.sd = self._real_sd


class TestInterrupt(PlaybackTestCase):
    def test_interrupt_never_calls_sounddevice_from_the_callers_thread(self):
        fake = FakeSoundDevice()
        self.install(fake)
        voice_engine.audio_queue.put((voice_engine._generation, "chunk"))
        self.assertTrue(wait_until(lambda: fake.played), "chunk was never played")

        calls_before = len(fake.calls)
        voice_engine.interrupt_audio()
        self.assertTrue(wait_until(lambda: any(n == "abort" for n, _ in fake.calls)),
                        "the playing chunk was never cut off")
        self.assertTrue(wait_until(lambda: fake.calls[-1][0] == "stop"))

        me = threading.get_ident()
        self.assertGreaterEqual(len(fake.calls) - calls_before, 2)   # abort, then stop
        threads = {ident for _, ident in fake.calls}
        self.assertEqual(len(threads), 1, "sounddevice was called from more than one thread")
        self.assertNotIn(me, threads)

    def test_chunks_queued_before_an_interrupt_are_never_played(self):
        fake = FakeSoundDevice(finish_instantly=True)
        self.install(fake)
        stale = voice_engine._generation
        voice_engine.interrupt_audio()
        voice_engine.audio_queue.put((stale, "stale"))
        voice_engine.audio_queue.put((voice_engine._generation, "fresh"))
        self.assertTrue(wait_until(lambda: "fresh" in fake.played))
        self.assertNotIn("stale", fake.played)

    def test_chunks_play_in_order(self):
        fake = FakeSoundDevice(finish_instantly=True)
        self.install(fake)
        for name in ("one", "two", "three"):
            voice_engine.audio_queue.put((voice_engine._generation, name))
        self.assertTrue(wait_until(lambda: len(fake.played) == 3))
        self.assertEqual(fake.played, ["one", "two", "three"])


class TestWorkerSurvivesErrors(PlaybackTestCase):
    def test_a_failing_chunk_does_not_kill_the_worker(self):
        """An exception used to end the worker thread, and the reader went mute for good."""
        fake = FakeSoundDevice(finish_instantly=True)
        real_play = fake.play

        def play(audio, samplerate):
            if audio == "bad":
                raise RuntimeError("device unplugged")
            real_play(audio, samplerate)
        fake.play = play
        self.install(fake)

        # assertLogs also keeps the expected error out of the real reader_debug.log.
        with self.assertLogs(level="ERROR") as logs:
            voice_engine.audio_queue.put((voice_engine._generation, "bad"))
            voice_engine.audio_queue.put((voice_engine._generation, "good"))
            self.assertTrue(wait_until(lambda: "good" in fake.played))
        self.assertIn("device unplugged", logs.output[0])


if __name__ == "__main__":
    unittest.main()
