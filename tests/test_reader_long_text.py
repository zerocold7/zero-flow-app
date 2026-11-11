"""Very long selections.

Measured before Phase 6 (RTX 4070): length did not slow the start (0.16 s to the first
sound at 5k, 20k and 50k characters), but every chunk was rendered ahead of playback
with no limit — about 6 MB of audio held per minute of speech, 296 MB for 50k
characters (51 minutes), and on the CPU a 50k read kept the processor busy for ~13
minutes. So a read is cut to READER_MAX_CHARS, and rendering stays only a few chunks
ahead of the speaker. No voice model is loaded and nothing is played.
"""
import os
import queue
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reader import app, text_cleaner, voice_engine


# ------------------------------------------------------------------------- the length limit
class TestTrimToLimit(unittest.TestCase):
    def test_text_within_the_limit_is_unchanged(self):
        self.assertEqual(text_cleaner.trim_to_limit("Short. Text.", 100), "Short. Text.")

    def test_long_text_ends_at_the_last_whole_sentence_that_fits(self):
        text = "First sentence. Second sentence! Third one is cut off here"
        self.assertEqual(text_cleaner.trim_to_limit(text, 40), "First sentence. Second sentence!")

    def test_arabic_sentence_ends_count(self):
        text = "جملة أولى؟ جملة ثانية طويلة جدا لا تتسع"
        self.assertEqual(text_cleaner.trim_to_limit(text, 20), "جملة أولى؟")

    def test_with_no_sentence_end_it_ends_at_a_word(self):
        self.assertEqual(text_cleaner.trim_to_limit("one two three four", 10), "one two")

    def test_one_endless_word_is_cut_at_the_limit(self):
        self.assertEqual(text_cleaner.trim_to_limit("x" * 50, 10), "x" * 10)

    def test_the_result_is_never_longer_than_the_limit(self):
        text = ("The committee met on Tuesday, and it agreed. " * 1000)
        for limit in (1, 7, 45, 46, 47, 500, 20000):
            self.assertLessEqual(len(text_cleaner.trim_to_limit(text, limit)), limit)


class TestTheReaderCutsLongSelections(unittest.TestCase):
    def press_f4(self, text):
        with mock.patch.object(app.signals, "is_recording", return_value=False), \
             mock.patch.object(app.keyboard, "release"), \
             mock.patch.object(app, "copy_selection", return_value=text), \
             mock.patch.object(app, "use_smart_mode", False), \
             mock.patch.object(app, "_title"), \
             mock.patch.object(app.ui, "play_tone"), \
             mock.patch.object(voice_engine, "stream_audio") as speak, \
             mock.patch("sys.stdout"):
            app.process_and_speak()
        return speak.call_args.args[0]

    def test_the_limit_is_twenty_thousand_characters(self):
        self.assertEqual(app.READER_MAX_CHARS, 20000)

    def test_a_selection_over_the_limit_is_read_only_up_to_it(self):
        text = "The committee met on Tuesday. " * 2000          # 60,000 characters
        with self.assertLogs(level="INFO") as logs:
            spoken = self.press_f4(text)
        self.assertLessEqual(len(spoken), app.READER_MAX_CHARS)
        self.assertGreater(len(spoken), app.READER_MAX_CHARS - 100)
        said = "\n".join(logs.output)
        self.assertIn("60000", said)
        self.assertNotIn("committee", said)                       # sizes only, never words

    def test_a_selection_within_the_limit_is_read_whole(self):
        text = "The committee met on Tuesday. " * 100
        self.assertEqual(self.press_f4(text), text.strip())


# ------------------------------------------------------------------- rendering stays ahead
class Overlap:
    """How many renders were under way at once, across every fake pipeline sharing it."""

    def __init__(self):
        self.running = self.most_at_once = 0
        self.lock = threading.Lock()


class Chunks:
    """A fake pipeline: `count` chunks per batch."""

    def __init__(self, count, name="chunk", overlap=None):
        self.count, self.name, self.overlap = count, name, overlap or Overlap()

    def __call__(self, batch, voice=None, speed=1.0):
        o = self.overlap
        with o.lock:
            o.running += 1
            o.most_at_once = max(o.most_at_once, o.running)
        try:
            for i in range(self.count):
                yield None, None, f"{self.name}{i}"
        finally:
            with o.lock:
                o.running -= 1


def wait_until(condition, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.005)
    return False


class AheadTestCase(unittest.TestCase):
    """The module's queue is swapped for a fresh one of the same size that nothing
    drains: the playback worker stays parked on the real one, so nothing is played."""

    def setUp(self):
        self.q = queue.Queue(maxsize=voice_engine.AHEAD_CHUNKS)
        for patcher in (mock.patch.object(voice_engine, "audio_queue", self.q),
                        mock.patch.object(voice_engine, "_voice", return_value="voice"),
                        mock.patch.object(voice_engine.signals, "set_reading")):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(voice_engine.interrupt_audio)

    def stream_in_thread(self, pipeline, text="One sentence."):
        generation = voice_engine.interrupt_audio()
        patcher = mock.patch.object(voice_engine, "get_pipeline", return_value=pipeline)
        patcher.start()
        self.addCleanup(patcher.stop)
        thread = threading.Thread(target=voice_engine.stream_audio, args=(text, generation),
                                  daemon=True)
        thread.start()
        return thread


class TestRenderingStaysAhead(AheadTestCase):
    def test_rendering_waits_when_the_speaker_is_behind(self):
        thread = self.stream_in_thread(Chunks(50))
        self.assertTrue(wait_until(self.q.full))
        time.sleep(0.1)
        self.assertTrue(thread.is_alive())                        # waiting, not done
        self.assertEqual(self.q.qsize(), voice_engine.AHEAD_CHUNKS)

    def test_an_interrupt_frees_a_render_that_is_waiting(self):
        thread = self.stream_in_thread(Chunks(50))
        self.assertTrue(wait_until(self.q.full))
        voice_engine.interrupt_audio()
        thread.join(1.0)
        self.assertFalse(thread.is_alive())

    def test_a_waiting_render_notices_the_interrupt_even_with_the_queue_still_full(self):
        thread = self.stream_in_thread(Chunks(50))
        self.assertTrue(wait_until(self.q.full))
        with mock.patch.object(voice_engine, "_generation", voice_engine._generation + 1):
            thread.join(1.0)                      # the generation moved; nothing was taken
            self.assertFalse(thread.is_alive())

    def test_a_new_read_waits_for_the_old_render_and_never_runs_beside_it(self):
        overlap = Overlap()
        first = self.stream_in_thread(Chunks(50, "old", overlap))
        self.assertTrue(wait_until(self.q.full))
        generation = voice_engine.interrupt_audio()
        new = Chunks(1, "new", overlap)
        with mock.patch.object(voice_engine, "get_pipeline", return_value=new):
            voice_engine.stream_audio("Next read.", generation)
        first.join(1.0)
        self.assertFalse(first.is_alive())
        # The old render may land one chunk after the interrupt; it carries the old
        # generation, which the playback worker drops unplayed.
        queued = [audio for g, audio in list(self.q.queue) if g == generation]
        self.assertEqual(queued, ["new0"])
        self.assertEqual(overlap.most_at_once, 1)                 # never two at once


class TestModuleQueue(unittest.TestCase):
    def test_the_module_queue_holds_only_a_few_chunks(self):
        self.assertEqual(voice_engine.audio_queue.maxsize, voice_engine.AHEAD_CHUNKS)
        self.assertGreaterEqual(voice_engine.AHEAD_CHUNKS, 2)
        self.assertLessEqual(voice_engine.AHEAD_CHUNKS, 8)


# ------------------------------------------------------------- F4 during a long read
class TestPressDuringALongRead(unittest.TestCase):
    """stream_audio now lasts as long as the speech. The press lock must not be held
    through it, or every F4 during a long read would be ignored."""

    def test_the_press_lock_is_free_while_speaking(self):
        seen = []
        with mock.patch.object(app.signals, "is_recording", return_value=False), \
             mock.patch.object(app.keyboard, "release"), \
             mock.patch.object(app, "copy_selection", return_value="Read this."), \
             mock.patch.object(app, "use_smart_mode", False), \
             mock.patch.object(app, "_title"), \
             mock.patch.object(app.ui, "play_tone"), \
             mock.patch.object(voice_engine, "stream_audio",
                               side_effect=lambda *a: seen.append(app.reading.locked())), \
             mock.patch("sys.stdout"):
            app.process_and_speak()
        self.assertEqual(seen, [False])

    def test_a_second_press_while_the_first_still_speaks_starts_a_new_read(self):
        speaking, finish = threading.Event(), threading.Event()
        reads = []

        def stream(text, generation):
            reads.append(generation)
            if len(reads) == 1:
                speaking.set()
                finish.wait(5)
        with mock.patch.object(app.signals, "is_recording", return_value=False), \
             mock.patch.object(app.keyboard, "release"), \
             mock.patch.object(app, "copy_selection", return_value="Read this."), \
             mock.patch.object(app, "use_smart_mode", False), \
             mock.patch.object(app, "_title"), \
             mock.patch.object(app.ui, "play_tone"), \
             mock.patch.object(voice_engine, "stream_audio", side_effect=stream), \
             mock.patch("sys.stdout"):
            first = threading.Thread(target=app.process_and_speak)
            first.start()
            self.assertTrue(speaking.wait(5))
            app.process_and_speak()
            finish.set()
            first.join(5)
        self.assertEqual(len(reads), 2)
        self.assertGreater(reads[1], reads[0])                    # the second interrupted


if __name__ == "__main__":
    unittest.main()
