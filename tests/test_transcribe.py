"""Transcription failures: the clip is recovered where it can be, and the log says
what really happened.

Whisper, Kokoro and the AI model share one graphics card. When it ran out of memory
mid-dictation, the clip was lost and the log blamed silence.
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import engine
from zeroflow import stt
from zeroflow import ui



def whisper_returning(text, language="en"):
    segment = mock.Mock(text=text)
    return mock.Mock(transcribe=mock.Mock(return_value=(iter([segment]), mock.Mock(language=language))))


def whisper_raising(error):
    return mock.Mock(transcribe=mock.Mock(side_effect=error))


class TranscribeTestCase(unittest.TestCase):
    def setUp(self):
        for patcher in (mock.patch.object(stt, "load_vocabulary", return_value=[]),
                        mock.patch.object(stt, "resolve_whisper_model", return_value="model-dir"),
                        mock.patch.object(stt, "_cpu_model", None, create=True)):
            patcher.start()
            self.addCleanup(patcher.stop)


class TestGpuOutOfMemory(TranscribeTestCase):
    def test_the_clip_is_transcribed_on_the_cpu_instead(self):
        gpu = whisper_raising(RuntimeError("CUDA failed with error out of memory"))
        cpu = whisper_returning(" Hello there.")
        with mock.patch.object(stt, "model", gpu), \
             mock.patch.object(stt, "model_runtime", "GPU · float16"), \
             mock.patch.object(stt, "WhisperModel", return_value=cpu) as build, \
             self.assertLogs(level="WARNING") as logs:
            text, lang = stt.transcribe_clip("en")
        self.assertEqual((text, lang), ("Hello there.", "en"))
        self.assertEqual(build.call_args.kwargs["device"], "cpu")
        self.assertIn("CPU", "\n".join(logs.output))

    def test_the_cpu_model_is_loaded_once(self):
        gpu = whisper_raising(RuntimeError("CUDA failed with error out of memory"))
        with mock.patch.object(stt, "model", gpu), \
             mock.patch.object(stt, "model_runtime", "GPU · float16"), \
             mock.patch.object(stt, "WhisperModel",
                               side_effect=lambda *a, **k: whisper_returning(" Hi.")) as build, \
             self.assertLogs(level="WARNING"):
            stt.transcribe_clip("en")
            stt.transcribe_clip("en")
        self.assertEqual(build.call_count, 1)

    def test_a_cpu_engine_does_not_retry_on_the_cpu(self):
        broken = whisper_raising(ValueError("bad audio"))
        with mock.patch.object(stt, "model", broken), \
             mock.patch.object(stt, "model_runtime", "CPU · int8"), \
             mock.patch.object(stt, "WhisperModel") as build, \
             self.assertLogs(level="ERROR"):
            self.assertEqual(stt.transcribe_clip("en"), (None, None))
        build.assert_not_called()


class TestFailureIsNotCalledSilence(TranscribeTestCase):
    def test_a_failed_transcription_is_logged_as_a_failure(self):
        """It was logged as "silence / VAD dropped all audio" — pointing at the mic."""
        handle, wav = tempfile.mkstemp(suffix=".wav")
        os.close(handle)
        self.addCleanup(lambda: os.path.exists(wav) and os.unlink(wav))
        broken = whisper_raising(ValueError("bad audio"))
        with mock.patch.object(stt, "model", broken), \
             mock.patch.object(stt, "model_runtime", "CPU · int8"), \
             mock.patch.object(stt, "TEMP_AUDIO_FILE", wav), \
             mock.patch.object(engine, "ENABLE_AUDIO_CHIMES", False), \
             mock.patch.object(ui, "update_console_title"), \
             mock.patch.object(engine, "inject_text") as inject, \
             mock.patch("sys.stdout"), \
             self.assertLogs(level="INFO") as logs:
            engine.transcribe_and_inject(np.full((16000, 1), 0.1, np.float32), "en_raw", "")
        log = "\n".join(logs.output)
        self.assertNotIn("silence", log)
        self.assertIn("Transcription failed", log)
        inject.assert_not_called()


if __name__ == "__main__":
    unittest.main()
