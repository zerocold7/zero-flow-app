"""The self-evolving vocabulary: [LEARN: word] absorption and the store behind it.

Each test redirects flow_core at a temporary vocabulary file, so the real
flow_vocabulary.txt is never touched.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flow_core
import personas


class VocabularyTestCase(unittest.TestCase):
    def setUp(self):
        handle, self.vocab_path = tempfile.mkstemp(suffix=".txt")
        os.close(handle)
        self._real_path = flow_core.VOCAB_CACHE_FILE
        flow_core.VOCAB_CACHE_FILE = self.vocab_path
        # Toasts would try to reach the Windows notification service; silence them.
        self._real_toasts = flow_core.ENABLE_TOASTS
        flow_core.ENABLE_TOASTS = False

    def tearDown(self):
        flow_core.VOCAB_CACHE_FILE = self._real_path
        flow_core.ENABLE_TOASTS = self._real_toasts
        try:
            os.unlink(self.vocab_path)
        except OSError:
            pass

    def read_vocab_file(self):
        with open(self.vocab_path, encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]


class TestAbsorbLearnedWord(VocabularyTestCase):
    def test_tag_is_stripped_from_the_output(self):
        """The tag is an instruction to us, not something to inject or speak."""
        out = flow_core._absorb_learned_word("Some prose [LEARN: ChromaDB]")
        self.assertNotIn("LEARN", out)
        self.assertEqual(out, "Some prose")

    def test_new_word_is_persisted(self):
        flow_core._absorb_learned_word("text [LEARN: Kokoro]")
        self.assertIn("Kokoro", self.read_vocab_file())

    def test_untagged_output_is_returned_unchanged(self):
        self.assertEqual(flow_core._absorb_learned_word("nothing to learn"),
                         "nothing to learn")

    def test_word_already_known_is_not_duplicated(self):
        flow_core._absorb_learned_word("a [LEARN: Kokoro]")
        flow_core._absorb_learned_word("b [LEARN: Kokoro]")
        self.assertEqual(self.read_vocab_file().count("Kokoro"), 1)

    def test_base_vocabulary_is_not_rewritten_to_the_file(self):
        """BASE_VOCABULARY lives in personas.py; re-learning it would be noise."""
        known = personas.BASE_VOCABULARY[0]
        flow_core._absorb_learned_word(f"x [LEARN: {known}]")
        self.assertNotIn(known, self.read_vocab_file())


class TestLoadVocabulary(VocabularyTestCase):
    def test_includes_the_base_list(self):
        vocab = flow_core.load_vocabulary()
        for word in personas.BASE_VOCABULARY:
            self.assertIn(word, vocab)

    def test_includes_learned_words(self):
        with open(self.vocab_path, "w", encoding="utf-8") as f:
            f.write("Manhwa\nTsukihime\n")
        vocab = flow_core.load_vocabulary()
        self.assertIn("Manhwa", vocab)
        self.assertIn("Tsukihime", vocab)

    def test_survives_a_missing_file(self):
        os.unlink(self.vocab_path)
        self.assertTrue(flow_core.load_vocabulary())        # base list still returned


if __name__ == "__main__":
    unittest.main()
