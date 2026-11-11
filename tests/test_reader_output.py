"""The Reader's output device, picked by name like the microphone (READER_OUTPUT).

A blank name is the Windows default. A name that is not plugged in when the Reader starts
falls back to the default for that run. A device that fails mid-read (headphones
unplugged) falls back to the default for the rest of the run, and the chunk that failed
is played again there, so the read carries on. Nothing is played: a fake sounddevice.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reader import voice_engine
from tests.test_playback import FakeSoundDevice, PlaybackTestCase, wait_until
from zeroflow import microphone, settings

DEVICES = [
    {"name": "Desk mic", "max_input_channels": 1, "max_output_channels": 0, "hostapi": 0},
    {"name": "Speakers", "max_input_channels": 0, "max_output_channels": 2, "hostapi": 0},
    {"name": "Headphones", "max_input_channels": 0, "max_output_channels": 2, "hostapi": 0},
    {"name": "Headphones", "max_input_channels": 0, "max_output_channels": 2, "hostapi": 2},
    {"name": "Headset", "max_input_channels": 1, "max_output_channels": 2, "hostapi": 0},
]


class TestOutputNames(unittest.TestCase):
    def test_only_devices_that_play_are_listed_each_once(self):
        self.assertEqual(microphone.output_names(DEVICES), ["Speakers", "Headphones", "Headset"])

    def test_the_microphone_list_is_unchanged(self):
        self.assertEqual(microphone.input_names(DEVICES), ["Desk mic", "Headset"])


class TestResolveOutput(unittest.TestCase):
    def test_blank_is_the_windows_default(self):
        self.assertEqual(microphone.resolve("", DEVICES, output=True), (None, False))

    def test_a_named_output_is_found_in_the_default_audio_system(self):
        self.assertEqual(microphone.resolve("Headphones", DEVICES, 2, output=True), (3, False))
        self.assertEqual(microphone.resolve("Headphones", DEVICES, 0, output=True), (2, False))

    def test_an_input_only_device_is_not_an_output(self):
        self.assertEqual(microphone.resolve("Desk mic", DEVICES, output=True), (None, True))

    def test_an_unplugged_output_falls_back(self):
        self.assertEqual(microphone.resolve("Old TV", DEVICES, output=True), (None, True))

    def test_a_microphone_is_still_resolved_as_an_input(self):
        self.assertEqual(microphone.resolve("Headset", DEVICES), (4, False))


class TestTheSetting(unittest.TestCase):
    def test_the_default_is_blank_the_windows_default(self):
        values, _ = settings.resolve({})
        self.assertEqual(values["READER_OUTPUT"], "")


class FakeOutputs(FakeSoundDevice):
    """Lists DEVICES; playing on a device in `broken` raises, like an unplugged one."""

    def __init__(self, broken=()):
        super().__init__(finish_instantly=True)
        self.broken, self.devices_used = set(broken), []
        self.default = mock.Mock(hostapi=0)

    def query_devices(self):
        return DEVICES

    def play(self, audio, samplerate, device=None):
        self.devices_used.append(device)
        if device in self.broken:
            raise RuntimeError("Error opening OutputStream: Device unavailable")
        super().play(audio, samplerate)


class OutputTestCase(PlaybackTestCase):
    def pick(self, name, broken=()):
        self.install(FakeOutputs(broken))
        for patcher in (mock.patch.object(voice_engine.settings, "READER_OUTPUT", name),
                        mock.patch.object(voice_engine, "_output", voice_engine.UNRESOLVED)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def play(self, *chunks):
        generation = voice_engine._generation
        for chunk in chunks:
            voice_engine.audio_queue.put((generation, chunk))
        self.assertTrue(wait_until(lambda: len(self.fake.played) >= len(chunks)))


class TestPlaybackDevice(OutputTestCase):
    def test_the_picked_device_is_used(self):
        self.pick("Headphones")
        self.play("a", "b")
        self.assertEqual(self.fake.devices_used[:2], [2, 2])

    def test_blank_plays_on_the_windows_default(self):
        self.pick("")
        self.play("a")
        self.assertEqual(self.fake.devices_used[0], None)

    def test_a_device_not_plugged_in_plays_on_the_default_and_says_so_once(self):
        self.pick("Old TV")
        with self.assertLogs(level="WARNING") as logs:
            self.play("a", "b")
        self.assertEqual(self.fake.devices_used[:2], [None, None])
        self.assertEqual(sum("Old TV" in line for line in logs.output), 1)

    def test_a_device_failing_mid_read_moves_to_the_default_and_replays_the_chunk(self):
        self.pick("Headphones", broken={2})
        with self.assertLogs(level="WARNING"):
            self.play("a", "b")
        self.assertEqual(self.fake.played[:2], ["a", "b"])        # nothing lost
        self.assertEqual(self.fake.devices_used[:3], [2, None, None])


if __name__ == "__main__":
    unittest.main()
