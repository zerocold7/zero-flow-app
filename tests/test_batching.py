"""Sentence batching — what decides how long you wait before the voice starts.

Importing reader.voice_engine pulls in sounddevice and starts the playback worker
thread, but no model: the pipeline is lazy, so these tests never touch torch or the GPU.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reader.voice_engine import _iter_batches


class TestIterBatches(unittest.TestCase):
    def test_empty_input_yields_nothing(self):
        self.assertEqual(list(_iter_batches("")), [])
        self.assertEqual(list(_iter_batches("   \n ")), [])

    def test_single_sentence_is_one_batch(self):
        self.assertEqual(list(_iter_batches("Just one sentence.")), ["Just one sentence."])

    def test_unterminated_text_still_speaks(self):
        """A selection without a full stop must not vanish."""
        self.assertEqual(list(_iter_batches("no terminator here")), ["no terminator here"])

    def test_first_batch_is_smaller_than_the_rest(self):
        """The first batch is the only one anybody waits on, so it is capped tighter."""
        text = " ".join(f"Sentence number {i} of the passage." for i in range(30))
        batches = list(_iter_batches(text, first_max=60, batch_max=200))
        self.assertGreater(len(batches), 2)
        self.assertLessEqual(len(batches[0]), 60 + 40)
        self.assertGreater(len(batches[1]), len(batches[0]))

    def test_never_splits_mid_sentence(self):
        """Splitting inside a sentence would audibly chop the phrasing."""
        text = ("First one here. Second one follows. Third arrives now. "
                "Fourth and final sentence of this passage.")
        for batch in _iter_batches(text, first_max=20, batch_max=20):
            self.assertNotEqual(batch.strip(), "")
            # every batch ends where a sentence ended, or is the tail of the text
            self.assertTrue(batch.rstrip().endswith(".") or batch in text)

    def test_no_text_is_lost(self):
        text = "Alpha one. Beta two! Gamma three? Delta four."
        joined = " ".join(_iter_batches(text, first_max=15, batch_max=15))
        for word in ("Alpha", "Beta", "Gamma", "Delta"):
            self.assertIn(word, joined)

    def test_splits_on_arabic_terminators(self):
        text = "هذا نص؟ وهذا أيضاً."
        self.assertEqual(len(list(_iter_batches(text, first_max=10, batch_max=10))), 2)

    def test_splits_on_hard_line_breaks(self):
        self.assertEqual(len(list(_iter_batches("Line one\nLine two", first_max=5, batch_max=5))), 2)


if __name__ == "__main__":
    unittest.main()
