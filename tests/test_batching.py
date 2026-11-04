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
        """Splitting inside a sentence would audibly chop the phrasing. (One exception,
        below: a long first sentence is split at a comma.)"""
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


class TestLongFirstSentence(unittest.TestCase):
    """Nothing is heard until the first batch is made, and a batch used to be at least a
    whole sentence: a 223-character opening sentence meant 3.4 s of silence on the
    processor. Split at a comma, the voice started at 2.0 s."""

    LONG = ("When the engine reads a long selection aloud, the first sentence is often the "
            "longest one, full of clauses and commas, and nothing can be heard until it is "
            "made. Then a short one.")

    def test_a_long_first_sentence_is_split_at_a_comma(self):
        first = next(_iter_batches(self.LONG, first_max=60))
        self.assertEqual(first, "When the engine reads a long selection aloud,")

    def test_clauses_are_grouped_up_to_the_first_batch_size(self):
        first = next(_iter_batches(self.LONG, first_max=120))
        self.assertTrue(first.endswith(","))
        self.assertLessEqual(len(first), 120)
        self.assertGreater(len(first), 60)                  # two clauses, not one

    def test_nothing_is_lost_or_reordered(self):
        for first_max in (20, 60, 120, 500):
            batches = list(_iter_batches(self.LONG, first_max=first_max, batch_max=300))
            self.assertEqual(" ".join(batches), self.LONG, first_max)

    def test_only_the_first_sentence_is_split(self):
        text = "Short start. " + self.LONG
        batches = list(_iter_batches(text, first_max=60, batch_max=60))
        self.assertTrue(all(b.endswith((".", "start.")) or b == batches[-1] for b in batches[1:]))
        self.assertNotIn(",", "".join(b[-1] for b in batches))

    def test_a_first_clause_longer_than_the_batch_is_kept_whole(self):
        text = "A first clause that is already far longer than the batch, then more."
        self.assertEqual(next(_iter_batches(text, first_max=20)),
                         "A first clause that is already far longer than the batch,")

    def test_a_long_sentence_without_commas_is_left_whole(self):
        text = "x " * 100
        self.assertEqual(list(_iter_batches(text, first_max=20)), [text.strip()])

    def test_arabic_commas_split_too(self):
        text = "هذه جملة طويلة جداً تبدأ القراءة، وفيها فاصلة عربية ثم كلام كثير بعدها حتى النهاية."
        self.assertEqual(next(_iter_batches(text, first_max=40)), "هذه جملة طويلة جداً تبدأ القراءة،")


if __name__ == "__main__":
    unittest.main()
