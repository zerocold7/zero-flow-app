"""The Reader falls back to the CPU when the graphics card fails, once, for the rest of
the run.

Measured before Phase 6: a CUDA failure while loading left no voice model, so every F4
tried the load again (~0.9 s) and failed again; a CUDA failure while speaking left the
broken GPU model loaded, so every F4 failed at once. Either way the Reader never spoke
until the Engine restarted. No voice model is loaded here: `_load` is replaced by fakes.
"""
import os
import queue
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reader import voice_engine


class FakePipeline:
    """Yields one chunk per batch, named after its device; `broken` raises instead."""

    def __init__(self, device, broken=False):
        self.device, self.broken, self.calls = device, broken, 0

    def __call__(self, batch, voice=None, speed=1.0):
        self.calls += 1
        if self.broken:
            raise RuntimeError("CUDA error: an illegal memory access was encountered")
        yield None, None, f"{self.device}:{batch}"


class FallbackTestCase(unittest.TestCase):
    def setUp(self):
        self.loaded = []
        for patcher in (mock.patch.object(voice_engine, "_pipeline", None),
                        mock.patch.object(voice_engine, "active_device", None),
                        mock.patch.object(voice_engine, "audio_queue", queue.Queue()),
                        mock.patch.object(voice_engine, "_voice", return_value="voice"),
                        mock.patch.object(voice_engine.signals, "set_reading"),
                        mock.patch("sys.stdout")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def use(self, resolved, load):
        """Resolve to `resolved`; `load(device)` builds the pipeline for a device."""
        def _load(device):
            self.loaded.append(device)
            return load(device)
        for patcher in (mock.patch.object(voice_engine, "resolve_device", return_value=resolved),
                        mock.patch.object(voice_engine, "_load", side_effect=_load)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def queued(self):
        return [audio for _, audio in list(voice_engine.audio_queue.queue)]

    def without_raising(self, call, *args):
        """The Reader must carry on: an exception escaping is the fallback failing."""
        try:
            return call(*args)
        except Exception as e:
            self.fail(f"raised instead of falling back to the CPU: {e!r}")


class TestLoadFails(FallbackTestCase):
    def test_a_card_that_fails_to_load_falls_back_to_the_cpu(self):
        def load(device):
            if device == "cuda":
                raise RuntimeError("CUDA error: out of memory")
            return FakePipeline(device)
        self.use("cuda", load)
        with self.assertLogs(level="WARNING") as logs:
            pipeline = self.without_raising(voice_engine.get_pipeline)
        self.assertEqual(pipeline.device, "cpu")
        self.assertEqual(voice_engine.active_device, "cpu")
        self.assertEqual(self.loaded, ["cuda", "cpu"])
        self.assertIn("CPU", "\n".join(logs.output))

    def test_the_next_read_does_not_try_the_card_again(self):
        def load(device):
            if device == "cuda":
                raise RuntimeError("CUDA error: out of memory")
            return FakePipeline(device)
        self.use("cuda", load)
        with self.assertLogs(level="WARNING"):
            voice_engine.get_pipeline()
        voice_engine.get_pipeline()
        voice_engine.get_pipeline()
        self.assertEqual(self.loaded, ["cuda", "cpu"])

    def test_a_cpu_that_fails_to_load_is_not_retried_as_a_fallback(self):
        def load(device):
            raise RuntimeError("no model files")
        self.use("cpu", load)
        with self.assertRaises(RuntimeError):
            voice_engine.get_pipeline()
        self.assertEqual(self.loaded, ["cpu"])

    def test_the_cpu_failing_after_the_card_raises_and_names_both(self):
        def load(device):
            raise RuntimeError(f"{device} failed")
        self.use("cuda", load)
        with self.assertLogs(level="WARNING"), self.assertRaises(RuntimeError):
            voice_engine.get_pipeline()
        self.assertEqual(self.loaded, ["cuda", "cpu"])


class TestSpeakFails(FallbackTestCase):
    def test_a_card_that_fails_while_speaking_switches_to_the_cpu_and_still_speaks(self):
        self.use("cuda", lambda device: FakePipeline(device, broken=device == "cuda"))
        with self.assertLogs(level="WARNING") as logs:
            self.without_raising(voice_engine.stream_audio, "Hello there.", voice_engine._generation)
        self.assertEqual(self.queued(), ["cpu:Hello there."])
        self.assertEqual(voice_engine.active_device, "cpu")
        self.assertIn("CPU", "\n".join(logs.output))

    def test_the_switch_carries_on_from_the_batch_that_failed_not_the_start(self):
        calls = []

        class FailsOnSecond(FakePipeline):
            def __call__(self, batch, voice=None, speed=1.0):
                calls.append((self.device, batch))
                if self.device == "cuda" and len(calls) == 2:
                    raise RuntimeError("CUDA error: device lost")
                yield None, None, f"{self.device}:{batch}"
        self.use("cuda", FailsOnSecond)
        text = "One. " + "Two " * 40 + "two. " + "Three " * 60 + "three."
        batches = list(voice_engine._iter_batches(text))
        self.assertEqual(len(batches), 3)
        with self.assertLogs(level="WARNING"):
            voice_engine.stream_audio(text, voice_engine._generation)
        self.assertEqual(self.queued(), [f"cuda:{batches[0]}", f"cpu:{batches[1]}",
                                         f"cpu:{batches[2]}"])

    def test_a_batch_that_fails_part_way_is_not_spoken_twice(self):
        class TwoChunks(FakePipeline):
            def __call__(self, batch, voice=None, speed=1.0):
                yield None, None, f"{self.device}:part1"
                if self.device == "cuda":
                    raise RuntimeError("CUDA error: device lost")
                yield None, None, f"{self.device}:part2"
        self.use("cuda", TwoChunks)
        with self.assertLogs(level="WARNING"):
            voice_engine.stream_audio("Hello there.", voice_engine._generation)
        self.assertEqual(self.queued(), ["cuda:part1", "cpu:part2"])

    def test_the_warm_up_failing_on_the_card_moves_to_the_cpu(self):
        self.use("cuda", lambda device: FakePipeline(device, broken=device == "cuda"))
        with self.assertLogs(level="WARNING"):
            voice_engine.preload()
        self.assertEqual(voice_engine.active_device, "cpu")
        self.assertEqual(self.loaded, ["cuda", "cpu"])

    def test_a_cpu_that_fails_while_speaking_raises_and_loads_nothing_more(self):
        self.use("cpu", lambda device: FakePipeline(device, broken=True))
        with self.assertRaises(RuntimeError):
            voice_engine.stream_audio("Hello there.", voice_engine._generation)
        self.assertEqual(self.loaded, ["cpu"])

    def test_after_the_switch_reads_go_straight_to_the_cpu(self):
        self.use("cuda", lambda device: FakePipeline(device, broken=device == "cuda"))
        with self.assertLogs(level="WARNING"):
            voice_engine.stream_audio("First.", voice_engine._generation)
        voice_engine.stream_audio("Second.", voice_engine._generation)
        self.assertEqual(self.queued(), ["cpu:First.", "cpu:Second."])
        self.assertEqual(self.loaded, ["cuda", "cpu"])


if __name__ == "__main__":
    unittest.main()
