"""Voice macros and spoken punctuation — the transformation between what you say
and what lands in the focused app.

Imports local_flow, which pulls in faster-whisper but does NOT load a model (that
happens in boot()), so these stay fast and never touch the GPU.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import local_flow


class TestLeadingMacros(unittest.TestCase):
    def test_new_line_sets_the_flag_and_is_stripped(self):
        text, lead_newline, _ = local_flow.apply_macros("new line hello there")
        self.assertTrue(lead_newline)
        self.assertNotIn("new line", text.lower())
        self.assertIn("hello there", text)

    def test_new_line_does_not_also_get_a_leading_space(self):
        """A shift+enter is sent instead, so a space would indent the new line."""
        text, lead_newline, _ = local_flow.apply_macros("new line hello")
        self.assertTrue(lead_newline)
        self.assertFalse(text.startswith(" "))

    def test_bullet_prefixes_and_strips(self):
        text, _, _ = local_flow.apply_macros("bullet buy milk")
        self.assertTrue(text.startswith("• "))
        self.assertIn("buy milk", text)

    def test_code_block_wraps_in_backticks(self):
        text, _, _ = local_flow.apply_macros("format code print hello")
        self.assertTrue(text.startswith("`") and text.endswith("`"))

    def test_macro_matching_is_case_insensitive(self):
        _, lead_newline, _ = local_flow.apply_macros("New Line hello")
        self.assertTrue(lead_newline)


class TestTrailingMacros(unittest.TestCase):
    def test_and_send_sets_the_flag_and_is_stripped(self):
        text, _, end_enter = local_flow.apply_macros("see you tomorrow and send")
        self.assertTrue(end_enter)
        self.assertNotIn("and send", text.lower())
        self.assertIn("see you tomorrow", text)

    def test_plain_text_sets_no_flags(self):
        text, lead_newline, end_enter = local_flow.apply_macros("just ordinary words")
        self.assertFalse(lead_newline)
        self.assertFalse(end_enter)
        self.assertIn("just ordinary words", text)


class TestPunctuation(unittest.TestCase):
    def test_trailing_period_becomes_punctuation(self):
        text, _, _ = local_flow.apply_macros("that is all period")
        self.assertTrue(text.rstrip().endswith("."))
        self.assertNotIn("period", text.lower())

    def test_trailing_question_mark(self):
        text, _, _ = local_flow.apply_macros("are you sure question mark")
        self.assertTrue(text.rstrip().endswith("?"))

    def test_period_inside_a_sentence_is_left_alone(self):
        """The map is anchored to the end of the string on purpose."""
        text, _, _ = local_flow.apply_macros("the period drama was good")
        self.assertIn("period drama", text)


class TestSpacing(unittest.TestCase):
    def test_leading_space_keeps_words_apart(self):
        """Injected text joins whatever is already at the cursor."""
        text, _, _ = local_flow.apply_macros("continuing the sentence")
        self.assertTrue(text.startswith(" "))

    def test_bullet_gets_no_leading_space(self):
        text, _, _ = local_flow.apply_macros("bullet an item")
        self.assertTrue(text.startswith("•"))


if __name__ == "__main__":
    unittest.main()
