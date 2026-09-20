"""Voice macros and spoken punctuation — the transformation between what you say
and what lands in the focused app.

Imports local_flow, which pulls in faster-whisper but does NOT load a model (that
happens in boot()), so these stay fast and never touch the GPU.
"""
import os
import sys
import unittest
from unittest import mock

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


class TestWhisperPunctuation(unittest.TestCase):
    """Whisper writes what it hears as punctuated sentences — most real transcripts
    end in "." or "?" — so a macro has to be found through that punctuation. Before
    this, "and send" and every spoken punctuation word almost never fired."""

    def test_leading_macro_takes_its_punctuation_with_it(self):
        text, lead_newline, _ = local_flow.apply_macros("New line. Hello there.")
        self.assertTrue(lead_newline)
        self.assertEqual(text, "Hello there.")

    def test_bullet_takes_its_punctuation_with_it(self):
        text, _, _ = local_flow.apply_macros("Bullet: buy milk.")
        self.assertEqual(text, "• buy milk.")

    def test_trailing_macro_before_whisper_full_stop(self):
        text, _, end_enter = local_flow.apply_macros("See you tomorrow and send.")
        self.assertTrue(end_enter)
        self.assertEqual(text, " See you tomorrow")

    def test_trailing_macro_drops_the_pause_comma(self):
        text, _, end_enter = local_flow.apply_macros("See you tomorrow, and send.")
        self.assertTrue(end_enter)
        self.assertEqual(text, " See you tomorrow")

    def test_trailing_macro_keeps_the_speakers_own_mark(self):
        text, _, end_enter = local_flow.apply_macros("Done! And send.")
        self.assertTrue(end_enter)
        self.assertEqual(text, " Done!")

    def test_spoken_period_after_whisper_comma(self):
        text, _, _ = local_flow.apply_macros("That is all, period.")
        self.assertEqual(text, " That is all.")

    def test_spoken_question_mark_after_whisper_question_mark(self):
        text, _, _ = local_flow.apply_macros("Are you sure? Question mark.")
        self.assertEqual(text, " Are you sure?")

    def test_spoken_comma_then_and_send(self):
        text, _, end_enter = local_flow.apply_macros("Hello comma and send.")
        self.assertTrue(end_enter)
        self.assertEqual(text, " Hello,")

    def test_arabic_spoken_comma(self):
        text, _, _ = local_flow.apply_macros("مرحبا فاصلة")
        self.assertEqual(text, " مرحبا،")

    def test_ordinary_sentence_keeps_whisper_punctuation(self):
        text, lead_newline, end_enter = local_flow.apply_macros("Did he save the file here?")
        self.assertEqual(text, " Did he save the file here?")
        self.assertFalse(lead_newline or end_enter)


class TestWholeWordTriggers(unittest.TestCase):
    """A trigger is a whole word. Prefix matching turned "Pointless" into "• less"."""

    def test_word_starting_with_point_is_not_a_bullet(self):
        text, _, _ = local_flow.apply_macros("Pointless meeting today.")
        self.assertEqual(text, " Pointless meeting today.")

    def test_word_starting_with_bullet_is_not_a_bullet(self):
        text, _, _ = local_flow.apply_macros("Bulletproof vest.")
        self.assertEqual(text, " Bulletproof vest.")

    def test_new_lines_is_not_the_new_line_macro(self):
        text, lead_newline, _ = local_flow.apply_macros("New lines of code are here.")
        self.assertFalse(lead_newline)
        self.assertEqual(text, " New lines of code are here.")

    def test_word_ending_in_and_send_is_not_the_macro(self):
        text, _, end_enter = local_flow.apply_macros("I paid a thousand send.")
        self.assertFalse(end_enter)
        self.assertIn("thousand send", text)


class TestVocabularyCasing(unittest.TestCase):
    def test_known_term_is_recased(self):
        text, _, _ = local_flow.apply_macros("push it to github")
        self.assertIn("GitHub", text)

    def test_learned_word_with_a_backslash_is_inserted_literally(self):
        """Learned words come from the LLM. Used as a re.sub template, a backslash
        in one raised 'bad escape' and the whole dictation was lost."""
        with mock.patch.object(local_flow, "load_vocabulary", return_value=[r"C:\Tools"]):
            text, _, _ = local_flow.apply_macros(r"open c:\tools now")
        self.assertIn(r"C:\Tools", text)


if __name__ == "__main__":
    unittest.main()
