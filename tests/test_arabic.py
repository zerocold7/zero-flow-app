"""Arabic end to end — what Whisper is primed with, what the AI is asked, and what
reaches the page.

Each test pins down a problem measured on the real models: an English hint that cost
Arabic recognition ~11 points of accuracy, a model that answered Arabic Polish in
Chinese, vowel marks nobody asked for, and spoken commands that fired on ordinary
Arabic sentences. No model is loaded; the AI and Whisper are stand-ins.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flow_core
import local_flow
import personas

VOCAB = ["Docker", "GitHub", "Python", "تمارا", "زيرو فلو"]


class TestWhisperHint(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(local_flow, "load_vocabulary", return_value=list(VOCAB))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_arabic_is_primed_with_arabic_only(self):
        hint = local_flow.whisper_hint("ar")
        self.assertTrue(hint.startswith(personas.ARABIC_WHISPER_HINT))
        self.assertIsNone(local_flow.LATIN_LETTERS.search(hint), hint)
        self.assertIn("تمارا", hint)                      # Arabic names still help spelling

    def test_english_is_primed_with_latin_terms_only(self):
        hint = local_flow.whisper_hint("en")
        self.assertEqual(hint, "Docker, GitHub, Python")

    def test_the_hint_is_the_same_every_run(self):
        """The vocabulary is a set; unsorted, the hint changed from one start to the next."""
        with mock.patch.object(local_flow, "load_vocabulary", return_value=list(reversed(VOCAB))):
            reordered = local_flow.whisper_hint("en")
        self.assertEqual(reordered, local_flow.whisper_hint("en"))

    def test_transcribe_clip_passes_the_arabic_hint_to_whisper(self):
        seen = {}

        def transcribe(path, **kwargs):
            seen.update(kwargs)
            return iter([]), mock.Mock(language="ar")
        with mock.patch.object(local_flow, "model", mock.Mock(transcribe=transcribe)):
            local_flow.transcribe_clip("ar")
        self.assertEqual(seen["language"], "ar")
        self.assertTrue(seen["initial_prompt"].startswith(personas.ARABIC_WHISPER_HINT))


class AITestCase(unittest.TestCase):
    """refine_text with the AI replaced by a canned answer, and no sound or toasts."""

    def setUp(self):
        for patcher in (mock.patch.object(local_flow, "ENABLE_TOASTS", False),
                        mock.patch.object(local_flow, "ENABLE_AUDIO_CHIMES", False),
                        mock.patch.object(local_flow.ui, "update_console_title")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def refine(self, text, mode, answer):
        calls = []

        def fake_ai(raw, context, prompt, **kw):
            calls.append(prompt)
            return raw if answer is None else answer    # None: "Ollama was unreachable"
        with mock.patch.object(local_flow, "query_ollama", side_effect=fake_ai):
            out = local_flow.refine_text(text, mode)
        return out, calls[0]


class TestArabicPolish(AITestCase):
    RAW = "يعني انا كنت ابغى اقول انو الاجتماع بكره"

    def test_uses_the_arabic_prompt(self):
        _, prompt = self.refine(self.RAW, "ar_polish", "أردت أن أقول إن الاجتماع غدًا.")
        self.assertIs(prompt, personas.ARABIC_POLISH_PROMPT)

    def test_english_polish_keeps_the_english_prompt(self):
        _, prompt = self.refine("um hello there", "en_polish", "Hello there.")
        self.assertIs(prompt, personas.STANDARD_SYSTEM_PROMPT)

    def test_a_chinese_answer_is_never_pasted(self):
        """qwen2.5:7b answered this very input in Chinese, 5 tries out of 5."""
        with self.assertLogs(level="WARNING"):
            out, _ = self.refine(self.RAW, "ar_polish", "الاجتماع将于新的一天上午十点召开")
        self.assertEqual(out, self.RAW)

    def test_vowel_marks_are_removed_but_tanween_fath_stays(self):
        out, _ = self.refine(self.RAW, "ar_polish", "لنُحدِّث الخادم جدًا.")
        self.assertEqual(out, "لنحدث الخادم جدًا.")

    def test_an_unreachable_ai_passes_the_words_through_quietly(self):
        with self.assertNoLogs(level="WARNING"):
            out, _ = self.refine(self.RAW, "ar_polish", None)
        self.assertEqual(out, self.RAW)


class TestTranslation(AITestCase):
    def test_to_arabic_rejects_an_answer_with_no_arabic(self):
        with self.assertLogs(level="WARNING"):
            out, _ = self.refine("Please publish it", "en2ar", "Please publish it now")
        self.assertEqual(out, "Please publish it")

    def test_to_arabic_rejects_chinese_mixed_in(self):
        with self.assertLogs(level="WARNING"):
            out, _ = self.refine("Publish it", "en2ar", "انشرها 请发布")
        self.assertEqual(out, "Publish it")

    def test_to_english_rejects_an_arabic_answer(self):
        with self.assertLogs(level="WARNING"):
            out, _ = self.refine("انشرها", "ar2en", "انشرها الآن")
        self.assertEqual(out, "انشرها")

    def test_a_good_translation_goes_through(self):
        out, prompt = self.refine("Publish it on Thursday", "en2ar", "انشرها يوم الخميس.")
        self.assertEqual(out, "انشرها يوم الخميس.")
        self.assertIs(prompt, personas.TRANSLATE_TO_AR_PROMPT)


class TestArabicSpokenCommands(unittest.TestCase):
    """Bullets only with "قائمة", code only with "تنسيق كود". The bare words started
    ordinary sentences and turned them into bullets or code."""

    def test_a_sentence_starting_with_nuqta_is_left_alone(self):
        text, _, _ = local_flow.apply_macros("نقطة البداية هي تثبيت البرنامج.")
        self.assertEqual(text, " نقطة البداية هي تثبيت البرنامج.")

    def test_qaima_makes_a_bullet(self):
        text, _, _ = local_flow.apply_macros("قائمة شراء الحليب")
        self.assertEqual(text, "• شراء الحليب")

    def test_a_sentence_starting_with_code_is_left_alone(self):
        text, _, _ = local_flow.apply_macros("كود الخصم لا يعمل.")
        self.assertEqual(text, " كود الخصم لا يعمل.")

    def test_tansiq_code_wraps_as_code(self):
        text, _, _ = local_flow.apply_macros("تنسيق كود print hello")
        self.assertEqual(text, "`print hello`")

    def test_nuqta_at_the_end_still_types_a_full_stop(self):
        text, _, _ = local_flow.apply_macros("انتهينا من العمل نقطة")
        self.assertEqual(text, " انتهينا من العمل.")


class TestOllamaRequest(unittest.TestCase):
    def setUp(self):
        for patcher in (mock.patch.object(flow_core.ui, "start_processing_spinner"),
                        mock.patch.object(flow_core.ui, "stop_processing_spinner"),
                        mock.patch.object(flow_core, "ENABLE_TOASTS", False),
                        mock.patch.object(flow_core, "_ollama_model", "some-model")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_thinking_is_off_and_the_model_stays_loaded(self):
        """A reasoning model otherwise writes ~800 hidden tokens first: 5-9 s, not 0.8."""
        reply = mock.Mock(status_code=200, json=lambda: {"response": "Hello."})
        with mock.patch.object(flow_core.requests, "post", return_value=reply) as post:
            flow_core.query_ollama("hello", None, "Polish this.")
        body = post.call_args.kwargs["json"]
        self.assertIs(body["think"], False)
        self.assertEqual(body["keep_alive"], flow_core.OLLAMA_KEEP_ALIVE)

    def test_warm_up_stays_quiet_when_ollama_is_down(self):
        with mock.patch.object(flow_core.requests, "post", side_effect=ConnectionError("refused")), \
             self.assertLogs(level="INFO") as logs:
            flow_core.warm_up_llm()                  # must not raise
        self.assertIn("warm-up skipped", logs.output[-1])


if __name__ == "__main__":
    unittest.main()
