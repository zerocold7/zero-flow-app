"""The reader's cases a user meets: Smart cleaning's four outcomes, suspend, the Smart
toggle, a voice change, which device the voice runs on, a failed warm-up, and the
silence watcher. No voice model is loaded and nothing is played."""
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reader import app, text_cleaner, voice_engine


class TestSmartCleaning(unittest.TestCase):
    """The AI strips page furniture, but the reader must always say something."""

    # With a link: only the instant clean removes it, so a fallback can be told apart
    # from the AI's own answer passed through.
    RAW = "Read this **now** please https://example.com/page"

    def clean(self, answer, max_chars=1000):
        with mock.patch.object(text_cleaner, "SMART_MODE_MAX_CHARS", max_chars), \
             mock.patch.object(text_cleaner.llm, "ask_ai", return_value=answer) as ask:
            return text_cleaner.clean_text_smart(self.RAW), ask

    def test_the_ais_answer_is_spoken_with_stray_markdown_removed(self):
        out, _ = self.clean("Read this **now**,   please.")
        self.assertEqual(out, "Read this now, please.")

    def test_no_answer_falls_back_to_the_instant_clean(self):
        out, _ = self.clean(None)
        self.assertEqual(out, text_cleaner.clean_text_instant(self.RAW))

    def test_the_text_handed_back_unchanged_falls_back_too(self):
        out, _ = self.clean(self.RAW)
        self.assertEqual(out, text_cleaner.clean_text_instant(self.RAW))

    def test_text_over_the_limit_never_waits_for_the_ai(self):
        out, ask = self.clean("ignored", max_chars=5)
        ask.assert_not_called()
        self.assertEqual(out, text_cleaner.clean_text_instant(self.RAW))


class ReaderTestCase(unittest.TestCase):
    def setUp(self):
        for patcher in (mock.patch.object(app, "is_suspended", False),
                        mock.patch.object(app, "use_smart_mode", False),
                        mock.patch("sys.stdout")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def press_f4(self):
        with mock.patch.object(app.signals, "is_recording", return_value=False), \
             mock.patch.object(app.keyboard, "release"), \
             mock.patch.object(app, "copy_selection", return_value="Some **text**.") as copy, \
             mock.patch.object(app, "clean_text_smart", return_value="smart") as smart, \
             mock.patch.object(app, "_title"), \
             mock.patch.object(app.ui, "play_tone"), \
             mock.patch.object(voice_engine, "stream_audio") as speak:
            app.process_and_speak()
        return copy, smart, speak


class TestTrayToggles(ReaderTestCase):
    def test_suspended_the_read_key_does_nothing_and_speech_stops(self):
        with mock.patch.object(voice_engine, "interrupt_audio") as stop:
            app.toggle_suspend(None, None)
        stop.assert_called_once()
        copy, _, speak = self.press_f4()
        copy.assert_not_called()
        speak.assert_not_called()
        with mock.patch.object(voice_engine, "interrupt_audio"):
            app.toggle_suspend(None, None)                # and back on
        copy, _, speak = self.press_f4()
        speak.assert_called_once()

    def test_smart_cleaning_is_used_once_switched_on(self):
        _, smart, speak = self.press_f4()
        smart.assert_not_called()
        self.assertEqual(speak.call_args.args[0], "Some text.")
        app.toggle_smart_mode(None, None)
        _, smart, speak = self.press_f4()
        smart.assert_called_once()
        self.assertEqual(speak.call_args.args[0], "smart")

    def test_a_voice_picked_in_the_menu_is_used(self):
        with mock.patch.object(voice_engine, "current_voice", "af_heart"), \
             mock.patch("sys.stdout"):
            app.change_voice(None, types.SimpleNamespace(text="British Female (Emma)"))
            self.assertEqual(voice_engine.current_voice, "bf_emma")


class TestVoiceDevice(unittest.TestCase):
    def device(self, policy, cuda_build="12.6", card=True):
        torch = types.SimpleNamespace(version=types.SimpleNamespace(cuda=cuda_build),
                                      cuda=types.SimpleNamespace(is_available=lambda: card))
        with mock.patch.object(voice_engine, "DEVICE_POLICY", policy), \
             mock.patch.dict(sys.modules, {"torch": torch}):
            return voice_engine.resolve_device()

    def test_auto_uses_the_card_when_there_is_one(self):
        self.assertEqual(self.device("auto"), "cuda")
        self.assertEqual(self.device("auto", card=False), "cpu")

    def test_cpu_and_cuda_are_honoured(self):
        self.assertEqual(self.device("cpu"), "cpu")
        self.assertEqual(self.device("cuda"), "cuda")

    def test_the_cpu_only_torch_build_is_named_not_hidden(self):
        with self.assertLogs(level="WARNING") as logs:
            self.assertEqual(self.device("auto", cuda_build=None), "cpu")
        self.assertIn("CPU-only build of torch", "\n".join(logs.output))


class TestWarmUpAndSilence(unittest.TestCase):
    def test_a_failed_warm_up_is_logged_and_the_reader_carries_on(self):
        with mock.patch.object(voice_engine, "get_pipeline", side_effect=RuntimeError("no model")), \
             self.assertLogs(level="ERROR") as logs:
            voice_engine.preload()                        # does not raise
        self.assertIn("no model", "\n".join(logs.output))

    def test_dictation_starting_stops_the_voice(self):
        requests = iter([True, True])

        def wait():
            try:
                return next(requests)
            except StopIteration:
                raise SystemExit from None               # end the endless watcher
        with mock.patch.object(app.signals, "available", return_value=True), \
             mock.patch.object(app.signals, "wait_for_silence_request", side_effect=wait), \
             mock.patch.object(voice_engine, "interrupt_audio") as stop, \
             self.assertRaises(SystemExit):
            app.watch_for_silence_requests()
        self.assertEqual(stop.call_count, 2)

    def test_without_signalling_the_watcher_ends(self):
        with mock.patch.object(app.signals, "available", return_value=False), \
             mock.patch.object(app.signals, "wait_for_silence_request") as wait:
            app.watch_for_silence_requests()
        wait.assert_not_called()


if __name__ == "__main__":
    unittest.main()
