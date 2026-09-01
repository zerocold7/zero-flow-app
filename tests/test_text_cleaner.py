"""Reader text clean-up — the regex pass that runs before every spoken word."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import personas
from reader.text_cleaner import clean_text_instant, fix_pronunciation


class TestPronunciation(unittest.TestCase):
    def test_matches_regardless_of_case(self):
        """The map is written in one casing; real text is not. 'aqeeq' used to be
        fixed while 'Aqeeq' sailed through untouched."""
        self.assertEqual(fix_pronunciation("aqeeq"), "ah-keek")
        self.assertEqual(fix_pronunciation("Aqeeq"), "ah-keek")
        self.assertEqual(fix_pronunciation("AQEEQ"), "ah-keek")

    def test_respects_word_boundaries(self):
        """A bare str.replace would rewrite the middle of a longer word."""
        self.assertEqual(fix_pronunciation("Nasuverse"), "Nasuverse")
        self.assertIn("Nah-soo", fix_pronunciation("Nasu wrote it"))

    def test_leaves_unknown_words_alone(self):
        self.assertEqual(fix_pronunciation("ordinary words here"), "ordinary words here")

    def test_every_map_entry_is_reachable(self):
        for word in personas.PRONUNCIATION_MAP:
            self.assertNotEqual(fix_pronunciation(word), word,
                                f"{word!r} in PRONUNCIATION_MAP is never applied")


class TestCleanTextInstant(unittest.TestCase):
    def test_strips_urls(self):
        self.assertNotIn("http", clean_text_instant("See https://example.com/x now"))

    def test_strips_markdown_furniture(self):
        self.assertEqual(clean_text_instant("**Bold** and _italic_"), "Bold and italic")

    def test_drops_footnote_markers_whole(self):
        """Stripping only the brackets left the digits, and the voice read '[1]'
        aloud as 'one'."""
        self.assertEqual(clean_text_instant("Disputed [1] by some."), "Disputed by some.")
        self.assertEqual(clean_text_instant("Sources [2, 3] agree."), "Sources agree.")

    def test_no_orphan_space_before_punctuation(self):
        """Removing a marker mid-sentence used to strand a space: 'disputed .'"""
        self.assertEqual(clean_text_instant("It was disputed [4]."), "It was disputed.")

    def test_collapses_whitespace(self):
        self.assertEqual(clean_text_instant("too    many\n\nspaces"), "too many spaces")

    def test_handles_empty_input(self):
        self.assertEqual(clean_text_instant(""), "")
        self.assertEqual(clean_text_instant("   \n  "), "")


if __name__ == "__main__":
    unittest.main()
