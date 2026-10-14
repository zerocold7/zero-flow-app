"""The self-evolving vocabulary: [LEARN: word] absorption and the store behind it.

Each test redirects flow_core at a temporary vocabulary file, so the real
flow_vocabulary.txt is never touched.
"""
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import engine
from zeroflow import personas
from zeroflow import ui
from zeroflow import vocabulary



class VocabularyTestCase(unittest.TestCase):
    def setUp(self):
        handle, self.vocab_path = tempfile.mkstemp(suffix=".txt")
        os.close(handle)
        self._real_path = vocabulary.VOCAB_CACHE_FILE
        vocabulary.VOCAB_CACHE_FILE = self.vocab_path
        # Toasts would try to reach the Windows notification service; silence them.
        self._real_toasts = vocabulary.ENABLE_TOASTS
        vocabulary.ENABLE_TOASTS = False

    def tearDown(self):
        vocabulary.VOCAB_CACHE_FILE = self._real_path
        vocabulary.ENABLE_TOASTS = self._real_toasts
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
        out = vocabulary._absorb_learned_word("Some prose [LEARN: ChromaDB]")
        self.assertNotIn("LEARN", out)
        self.assertEqual(out, "Some prose")

    def test_new_word_is_persisted(self):
        vocabulary._absorb_learned_word("text [LEARN: Kokoro]")
        self.assertIn("Kokoro", self.read_vocab_file())

    def test_untagged_output_is_returned_unchanged(self):
        self.assertEqual(vocabulary._absorb_learned_word("nothing to learn"),
                         "nothing to learn")

    def test_word_already_known_is_not_duplicated(self):
        vocabulary._absorb_learned_word("a [LEARN: Kokoro]")
        vocabulary._absorb_learned_word("b [LEARN: Kokoro]")
        self.assertEqual(self.read_vocab_file().count("Kokoro"), 1)

    def test_base_vocabulary_is_not_rewritten_to_the_file(self):
        """BASE_VOCABULARY lives in personas.py; re-learning it would be noise."""
        known = personas.BASE_VOCABULARY[0]
        vocabulary._absorb_learned_word(f"x [LEARN: {known}]")
        self.assertNotIn(known, self.read_vocab_file())


class TestLearnOnlyWhatWasSaid(VocabularyTestCase):
    """A learned word becomes part of Whisper's hint on every later dictation, so the
    LLM may only teach words that were actually said. Arabic Polish once taught three
    misheard words; a model answering in Chinese tagged a Chinese one."""

    def test_a_word_nobody_said_is_not_learned(self):
        out = vocabulary._absorb_learned_word("Polished text [LEARN: Kubernetes]",
                                             heard="please restart the server")
        self.assertEqual(out, "Polished text")
        self.assertNotIn("Kubernetes", self.read_vocab_file())

    def test_a_word_that_was_said_is_learned_despite_spacing(self):
        vocabulary._absorb_learned_word("x [LEARN: KokoroTTS]", heard="the kokoro tts voice")
        self.assertIn("KokoroTTS", self.read_vocab_file())

    def test_chinese_is_never_learned(self):
        vocabulary._absorb_learned_word("x [LEARN: 会议]", heard="会议")
        self.assertEqual(self.read_vocab_file(), [])


class TestSafeAppend(VocabularyTestCase):
    """Appending a learned word must never damage the words already there."""

    def test_word_lands_on_its_own_line_when_the_file_lacks_a_final_newline(self):
        """A hand-edited file often ends without a newline ("...Visa"); appending
        straight onto it produced "VisaKokoro" — one wrong word instead of two."""
        with open(self.vocab_path, "w", encoding="utf-8") as f:
            f.write("Docker\nVisa")
        vocabulary._absorb_learned_word("text [LEARN: Kokoro]", heard="kokoro")
        self.assertEqual(self.read_vocab_file(), ["Docker", "Visa", "Kokoro"])

    def test_writers_wait_for_the_vocabulary_lock(self):
        """Shift+F1 rewrites the whole file while a dictation may be appending to it;
        both go through one lock so neither loses the other's change."""
        vocabulary.VOCAB_LOCK.acquire()
        writer = threading.Thread(target=vocabulary._absorb_learned_word,
                                  args=("x [LEARN: Kokoro]",), kwargs={"heard": "kokoro"})
        try:
            writer.start()
            writer.join(0.3)
            self.assertNotIn("Kokoro", self.read_vocab_file())   # still waiting
        finally:
            vocabulary.VOCAB_LOCK.release()
        writer.join(2)
        self.assertIn("Kokoro", self.read_vocab_file())


class TestLoadVocabulary(VocabularyTestCase):
    def test_includes_the_base_list(self):
        vocab = vocabulary.load_vocabulary()
        for word in personas.BASE_VOCABULARY:
            self.assertIn(word, vocab)

    def test_includes_learned_words(self):
        with open(self.vocab_path, "w", encoding="utf-8") as f:
            f.write("Manhwa\nTsukihime\n")
        vocab = vocabulary.load_vocabulary()
        self.assertIn("Manhwa", vocab)
        self.assertIn("Tsukihime", vocab)

    def test_survives_a_missing_file(self):
        os.unlink(self.vocab_path)
        self.assertTrue(vocabulary.load_vocabulary())        # base list still returned


class TestMemoryMaintenance(VocabularyTestCase):
    """Shift+F1 lets the LLM rewrite the whole learned-vocabulary file."""

    def setUp(self):
        super().setUp()
        with open(self.vocab_path, "w", encoding="utf-8") as f:
            f.write("Manhwa\n")
        for patcher in (mock.patch.object(engine, "VOCAB_CACHE_FILE", self.vocab_path),
                        mock.patch.object(engine, "ENABLE_TOASTS", False),
                        mock.patch.object(engine, "ENABLE_AUDIO_CHIMES", False),
                        mock.patch.object(ui, "update_console_title")):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(lambda: os.path.exists(self.backup) and os.unlink(self.backup))

    @property
    def backup(self):
        return self.vocab_path + ".bak"

    def run_maintenance(self, llm_output):
        with mock.patch.object(engine, "query_ollama", return_value=llm_output):
            engine.run_memory_maintenance()

    def test_list_markers_are_stripped(self):
        """Models answer "list the words" with "- word" / "1. word"."""
        self.run_maintenance("- Docker\n2. Python\n3.5-turbo\n\n* Kokoro")
        self.assertEqual(self.read_vocab_file(), ["Docker", "Python", "3.5-turbo", "Kokoro"])

    def test_the_models_chatter_is_not_kept_as_vocabulary(self):
        """Models wrap the list in a sentence or two. Kept, those lines became
        "words" and were fed to Whisper as hints on every later dictation."""
        self.run_maintenance("Here is the cleaned list:\nDocker\nVisual Studio Code\n"
                             "I removed the duplicates and sorted the remaining terms for you.")
        self.assertEqual(self.read_vocab_file(), ["Docker", "Visual Studio Code"])

    def test_previous_list_is_backed_up(self):
        self.run_maintenance("Docker")
        with open(self.backup, encoding="utf-8") as f:
            self.assertEqual(f.read(), "Manhwa\n")

    def test_unchanged_output_writes_nothing(self):
        """query_ollama returns its input when Ollama is down — that is not a success."""
        current = "\n".join(sorted(vocabulary.load_vocabulary()))
        self.run_maintenance(current)
        self.assertEqual(self.read_vocab_file(), ["Manhwa"])
        self.assertFalse(os.path.exists(self.backup))


if __name__ == "__main__":
    unittest.main()
