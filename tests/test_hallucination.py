"""Invented endings: "Thank you." / "شكرا للمشاهدة" written after a dictation, when
nobody said them.

Whisper learned from subtitled videos, and a breath, a keystroke or room noise after
you stop talking is where it writes the stock phrase those videos end with. A phrase
like that is dropped only when it ends the dictation AND the evidence says it was
never said: it sits on audio far quieter than the speech before it, or Whisper itself
was unsure of it. A clearly spoken "thank you" always stays.

The clips here are built sample by sample — loud where words were "said", quiet
where the tail was a breath — and the words carry the timings Whisper would give them.
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import stt

from faster_whisper.transcribe import Segment, Word

RATE = stt.SAMPLE_RATE


def clip(*parts):
    """Audio from (seconds, level) parts: level is the speech's RMS, 0 for silence."""
    rng = np.random.default_rng(7)
    return np.concatenate([rng.standard_normal(int(s * RATE)).astype(np.float32) * level
                           for s, level in parts])


def words(*timed):
    """Words from (text, start, end[, probability]) — Whisper's own word records."""
    return [Word(start=w[1], end=w[2], word=w[0], probability=w[3] if len(w) > 3 else 0.95)
            for w in timed]


SENTENCE = [(" Send", 0.0, 0.4), (" the", 0.4, 0.6), (" report", 0.6, 1.1),
            (" today.", 1.1, 1.8)]
SPEECH = (1.8, 0.1)                                   # 1.8 s of speech at RMS 0.1


def text_of(kept):
    return "".join(w.word for w in kept).strip()


class TestInventedEndings(unittest.TestCase):
    def test_thank_you_on_a_breath_is_dropped(self):
        audio = clip(SPEECH, (1.0, 0.0005), (0.6, 0.004), (0.5, 0.0005))
        kept = stt.trim_invented_ending(
            words(*SENTENCE, (" Thank", 2.8, 3.1), (" you.", 3.1, 3.4)), audio)
        self.assertEqual(text_of(kept), "Send the report today.")

    def test_a_clearly_spoken_thank_you_stays(self):
        audio = clip(SPEECH, (0.7, 0.09))
        kept = stt.trim_invented_ending(
            words(*SENTENCE, (" Thank", 1.8, 2.1), (" you.", 2.1, 2.5)), audio)
        self.assertEqual(text_of(kept), "Send the report today. Thank you.")

    def test_an_ending_whisper_was_unsure_of_is_dropped(self):
        """Loud enough — typing, say — but Whisper's own confidence gives it away."""
        audio = clip(SPEECH, (1.0, 0.08))
        kept = stt.trim_invented_ending(
            words(*SENTENCE, (" Have", 2.0, 2.2, 0.21), (" a", 2.2, 2.3, 0.30),
                  (" good", 2.3, 2.5, 0.25), (" night.", 2.5, 2.8, 0.18)), audio)
        self.assertEqual(text_of(kept), "Send the report today.")

    def test_thank_you_in_the_middle_is_never_touched(self):
        """Even when what follows it is quiet and unsure: only an ending is a candidate."""
        audio = clip((0.5, 0.1), (1.0, 0.002))
        sentence = words((" Thank", 0.0, 0.3), (" you", 0.3, 0.5), (" for", 0.5, 0.7, 0.3),
                         (" the", 0.7, 0.8, 0.3), (" report.", 0.8, 1.4, 0.3))
        self.assertEqual(text_of(stt.trim_invented_ending(sentence, audio)),
                         "Thank you for the report.")

    def test_an_ordinary_last_word_is_never_touched(self):
        """Only the known stock endings are candidates, however quiet the last word."""
        audio = clip(SPEECH, (1.0, 0.0005))
        kept = stt.trim_invented_ending(
            words(*SENTENCE[:3], (" tomorrow.", 1.8, 2.6, 0.4)), audio)
        self.assertEqual(text_of(kept), "Send the report tomorrow.")

    def test_arabic_subscribe_to_the_channel_is_dropped(self):
        audio = clip((2.0, 0.1), (1.5, 0.0008))
        sentence = words((" أرسل", 0.0, 0.5), (" التقرير", 0.5, 1.2), (" اليوم.", 1.2, 2.0),
                         (" اشتركوا", 2.3, 2.8), (" في", 2.8, 2.9), (" القناة", 2.9, 3.4))
        self.assertEqual(text_of(stt.trim_invented_ending(sentence, audio)),
                         "أرسل التقرير اليوم.")

    def test_arabic_spelling_variants_still_match(self):
        """Whisper writes "إلى" and "شكراً" as often as "الى" and "شكرا"."""
        audio = clip((2.0, 0.1), (1.5, 0.0008))
        sentence = words((" أرسل", 0.0, 0.5), (" التقرير", 0.5, 1.2), (" اليوم.", 1.2, 2.0),
                         (" إلى", 2.4, 2.7), (" اللقاء.", 2.7, 3.3))
        self.assertEqual(text_of(stt.trim_invented_ending(sentence, audio)),
                         "أرسل التقرير اليوم.")

    def test_arabic_thanks_said_aloud_stays(self):
        audio = clip((2.6, 0.1))
        sentence = words((" شكرا", 0.0, 0.6), (" جزيلا", 0.6, 1.2), (" على", 1.2, 1.5),
                         (" مساعدتك.", 1.5, 2.3), (" شكرا.", 2.3, 2.6))
        self.assertEqual(text_of(stt.trim_invented_ending(sentence, audio)),
                         "شكرا جزيلا على مساعدتك. شكرا.")

    def test_a_clip_that_is_only_an_invented_phrase_comes_out_empty(self):
        """Nothing was said: a breath was all the voice filter let through."""
        audio = clip((0.6, 0.0004), (0.8, 0.003), (0.6, 0.0004))
        kept = stt.trim_invented_ending(
            words((" Thank", 0.7, 1.0, 0.4), (" you.", 1.0, 1.3, 0.35)), audio)
        self.assertEqual(text_of(kept), "")

    def test_a_clip_that_is_only_a_clear_thank_you_stays(self):
        audio = clip((0.2, 0.0005), (0.8, 0.1), (0.2, 0.0005))
        kept = stt.trim_invented_ending(
            words((" Thank", 0.2, 0.55), (" you.", 0.55, 1.0)), audio)
        self.assertEqual(text_of(kept), "Thank you.")


class TestTranscribeUsesTheFilter(unittest.TestCase):
    def test_transcribe_audio_drops_an_invented_ending(self):
        """End to end through the engine's own transcription path."""
        audio = clip(SPEECH, (1.0, 0.0005), (0.6, 0.004), (0.5, 0.0005))
        segment = Segment(
            id=1, seek=0, start=0.0, end=3.4, text=" Send the report today. Thank you.",
            tokens=[], temperature=0.0, avg_logprob=-0.3, compression_ratio=1.2,
            no_speech_prob=0.05,
            words=words(*SENTENCE, (" Thank", 2.8, 3.1), (" you.", 3.1, 3.4)))
        model = unittest.mock.Mock()
        model.transcribe.return_value = (iter([segment]), unittest.mock.Mock(language="en"))
        with unittest.mock.patch.object(stt, "model", model), \
             unittest.mock.patch.object(stt, "load_vocabulary", return_value=[]), \
             self.assertLogs(level="INFO") as logs:
            text, _ = stt.transcribe_audio(audio, "en")
        self.assertEqual(text, "Send the report today.")
        self.assertTrue(model.transcribe.call_args.kwargs["word_timestamps"])
        self.assertIn("Thank you.", "\n".join(logs.output))     # the log says what was cut


import unittest.mock  # noqa: E402  (used above through unittest.mock)

if __name__ == "__main__":
    unittest.main()
