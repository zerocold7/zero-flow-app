"""Arabic end to end — what Whisper is primed with, what the AI is asked, and what
reaches the page.

Each test pins down a problem measured on the real models: an English hint that cost
Arabic recognition ~11 points of accuracy, a model that answered Arabic Polish in
Chinese, vowel marks nobody asked for, and spoken commands that fired on ordinary
Arabic sentences. No model is loaded; the AI and Whisper are stand-ins.
"""
import contextlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import clipboard
from zeroflow import engine
from zeroflow import hotkeys
from zeroflow import personas
from zeroflow import stt
from zeroflow import ui
from zeroflow.llm import ollama
from zeroflow.text import language
from zeroflow.text import macros


VOCAB = ["Docker", "GitHub", "Python", "تمارا", "زيرو فلو"]


class TestWhisperHint(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(stt, "load_vocabulary", return_value=list(VOCAB))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_arabic_is_primed_with_arabic_only(self):
        hint = stt.whisper_hint("ar")
        self.assertTrue(hint.startswith(personas.ARABIC_WHISPER_HINT))
        self.assertIsNone(language.LATIN_LETTERS.search(hint), hint)
        self.assertIn("تمارا", hint)                      # Arabic names still help spelling

    def test_english_is_primed_with_latin_terms_only(self):
        hint = stt.whisper_hint("en")
        self.assertEqual(hint, "Docker, GitHub, Python")

    def test_the_hint_is_the_same_every_run(self):
        """The vocabulary is a set; unsorted, the hint changed from one start to the next."""
        with mock.patch.object(stt, "load_vocabulary", return_value=list(reversed(VOCAB))):
            reordered = stt.whisper_hint("en")
        self.assertEqual(reordered, stt.whisper_hint("en"))

    def test_transcribe_clip_passes_the_arabic_hint_to_whisper(self):
        seen = {}

        def transcribe(path, **kwargs):
            seen.update(kwargs)
            return iter([]), mock.Mock(language="ar")
        with mock.patch.object(stt, "model", mock.Mock(transcribe=transcribe)):
            stt.transcribe_clip("ar")
        self.assertEqual(seen["language"], "ar")
        self.assertTrue(seen["initial_prompt"].startswith(personas.ARABIC_WHISPER_HINT))


class AITestCase(unittest.TestCase):
    """refine_text with the AI replaced by a canned answer, and no sound or toasts."""

    def setUp(self):
        for patcher in (mock.patch.object(engine, "ENABLE_TOASTS", False),
                        mock.patch.object(engine, "ENABLE_AUDIO_CHIMES", False),
                        mock.patch.object(ui, "update_console_title")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def refine(self, text, mode, answer):
        """refine_text with the AI answering `answer` (None: the AI was unreachable).
        What it printed is kept in self.printed."""
        calls = []

        def fake_ai(raw, context, prompt, **kw):
            calls.append(prompt)
            return answer
        console = io.StringIO()
        with mock.patch.object(engine, "ask_ollama", side_effect=fake_ai), \
             contextlib.redirect_stdout(console):
            out = engine.refine_text(text, mode)
        self.printed = console.getvalue()
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

    def test_an_unreachable_ai_is_reported_not_called_polished(self):
        """It used to print "✨ Polished" and play the success tone over your own,
        unchanged words — so nothing told you the AI was not running."""
        self.refine(self.RAW, "ar_polish", None)
        self.assertNotIn("Polished", self.printed)
        self.assertIn("AI unavailable", self.printed)


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

    def test_an_unreachable_ai_is_reported_not_called_translated(self):
        """The untranslated words are pasted; the console must say so."""
        out, _ = self.refine("Publish it", "en2ar", None)
        self.assertEqual(out, "Publish it")
        self.assertNotIn("Translated", self.printed)
        self.assertIn("AI unavailable", self.printed)

    def test_a_good_translation_goes_through(self):
        out, prompt = self.refine("Publish it on Thursday", "en2ar", "انشرها يوم الخميس.")
        self.assertEqual(out, "انشرها يوم الخميس.")
        self.assertIs(prompt, personas.TRANSLATE_TO_AR_PROMPT)


class TestArabicSpokenCommands(unittest.TestCase):
    """Bullets only with "قائمة", code only with "تنسيق كود". The bare words started
    ordinary sentences and turned them into bullets or code."""

    def test_a_sentence_starting_with_nuqta_is_left_alone(self):
        text, _, _ = macros.apply_macros("نقطة البداية هي تثبيت البرنامج.")
        self.assertEqual(text, " نقطة البداية هي تثبيت البرنامج.")

    def test_qaima_makes_a_bullet(self):
        text, _, _ = macros.apply_macros("قائمة شراء الحليب")
        self.assertEqual(text, "• شراء الحليب")

    def test_a_sentence_starting_with_code_is_left_alone(self):
        text, _, _ = macros.apply_macros("كود الخصم لا يعمل.")
        self.assertEqual(text, " كود الخصم لا يعمل.")

    def test_tansiq_code_wraps_as_code(self):
        text, _, _ = macros.apply_macros("تنسيق كود print hello")
        self.assertEqual(text, "`print hello`")

    def test_nuqta_at_the_end_still_types_a_full_stop(self):
        text, _, _ = macros.apply_macros("انتهينا من العمل نقطة")
        self.assertEqual(text, " انتهينا من العمل.")


class TestOllamaRequest(unittest.TestCase):
    def setUp(self):
        for patcher in (mock.patch.object(ui, "start_processing_spinner"),
                        mock.patch.object(ui, "stop_processing_spinner"),
                        mock.patch.object(ollama, "ENABLE_TOASTS", False),
                        mock.patch.object(ollama, "_ollama_model", "some-model")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_thinking_is_off_and_the_model_stays_loaded(self):
        """A reasoning model otherwise writes ~800 hidden tokens first: 5-9 s, not 0.8."""
        reply = mock.Mock(status_code=200, json=lambda: {"response": "Hello."})
        with mock.patch.object(ollama.requests, "post", return_value=reply) as post:
            ollama.query_ollama("hello", None, "Polish this.")
        body = post.call_args.kwargs["json"]
        self.assertIs(body["think"], False)
        self.assertEqual(body["keep_alive"], ollama.OLLAMA_KEEP_ALIVE)

    def test_the_context_is_sized_for_dictation(self):
        """The model file asks for 131,072 tokens; that cost 0.6 GB of graphics memory
        for nothing (3.58 GB → 2.99 GB measured, same speed and answers)."""
        reply = mock.Mock(status_code=200, json=lambda: {"response": "Hello."})
        with mock.patch.object(ollama, "OLLAMA_NUM_CTX", 8192, create=True), \
             mock.patch.object(ollama.requests, "post", return_value=reply) as post:
            ollama.query_ollama("hello", None, "Polish this.")
        self.assertEqual(post.call_args.kwargs["json"]["options"].get("num_ctx"), 8192)

    def test_warm_up_loads_the_model_exactly_as_requests_will_use_it(self):
        """A different context size makes Ollama reload the model — the first Polish
        would pay the 7 s load the warm-up was there to avoid."""
        reply = mock.Mock(status_code=200, json=lambda: {"response": "Hello."})
        with mock.patch.object(ollama, "OLLAMA_NUM_CTX", 8192, create=True), \
             mock.patch.object(ollama.requests, "post", return_value=reply) as post:
            ollama.warm_up_llm()
            ollama.query_ollama("hello", None, "Polish this.")
        warm, ask = (c.kwargs["json"] for c in post.call_args_list)
        self.assertEqual(warm.get("options"), ask["options"])
        self.assertEqual(warm["keep_alive"], ask["keep_alive"])

    def test_a_context_of_zero_keeps_the_models_own(self):
        reply = mock.Mock(status_code=200, json=lambda: {"response": "Hello."})
        with mock.patch.object(ollama, "OLLAMA_NUM_CTX", 0, create=True), \
             mock.patch.object(ollama.requests, "post", return_value=reply) as post:
            ollama.query_ollama("hello", None, "Polish this.")
        self.assertNotIn("num_ctx", post.call_args.kwargs["json"]["options"])

    def test_warm_up_stays_quiet_when_ollama_is_down(self):
        with mock.patch.object(ollama.requests, "post", side_effect=ConnectionError("refused")), \
             self.assertLogs(level="INFO") as logs:
            ollama.warm_up_llm()                  # must not raise
        self.assertIn("warm-up skipped", logs.output[-1])

    def test_warm_up_reports_a_model_ollama_does_not_have(self):
        """A 404 was logged as "loaded ahead of first use"."""
        reply = mock.Mock(status_code=404, text='{"error":"model not found"}')
        with mock.patch.object(ollama.requests, "post", return_value=reply), \
             self.assertLogs(level="INFO") as logs:
            ollama.warm_up_llm()
        self.assertNotIn("loaded ahead", "\n".join(logs.output))
        self.assertIn("404", "\n".join(logs.output))

    def test_an_empty_answer_counts_as_no_answer(self):
        """An empty reply would otherwise paste nothing at all."""
        reply = mock.Mock(status_code=200, json=lambda: {"response": "  "})
        with mock.patch.object(ollama.requests, "post", return_value=reply), \
             self.assertLogs(level="WARNING") as logs:
            self.assertIsNone(ollama.ask_ollama("hello", None, "Polish this."))
            self.assertEqual(ollama.query_ollama("hello", None, "Polish this."), "hello")
        self.assertIn("empty answer", logs.output[0])          # and the log says why


class TestModelDiscovery(unittest.TestCase):
    def setUp(self):
        # Fixed names, not the ones in your .env — there the fallback and the installed
        # model can be the same, which would let this pass without testing anything.
        for patcher in (mock.patch.object(ollama, "_ollama_model", None),
                        mock.patch.object(ollama, "OLLAMA_MODEL_NAME", ""),
                        mock.patch.object(ollama, "FALLBACK_LLM", "fallback-model")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_the_fallback_is_not_kept_once_ollama_is_running(self):
        """Ollama down at the first Polish bound the engine to FALLBACK_LLM for the rest
        of the session — every later request then got a 404."""
        tags = mock.Mock(status_code=200, json=lambda: {"models": [{"name": "installed-model"}]})
        with mock.patch.object(ollama.requests, "get",
                               side_effect=[ConnectionError("refused"), tags]):
            self.assertEqual(ollama.get_ollama_model(), "fallback-model")
            self.assertEqual(ollama.get_ollama_model(), "installed-model")

    def test_a_discovered_model_is_kept(self):
        """Once Ollama has answered, the engine stops asking."""
        tags = mock.Mock(status_code=200, json=lambda: {"models": [{"name": "installed-model"}]})
        with mock.patch.object(ollama.requests, "get", return_value=tags) as get:
            ollama.get_ollama_model()
            ollama.get_ollama_model()
        self.assertEqual(get.call_count, 1)


class TestFixLine(AITestCase):
    """Shift+F3: copy the line, let the AI fix it, paste it back."""

    def fix_line(self, line, answer):
        pasted = []
        with mock.patch.object(engine, "keyboard") as kb, \
             mock.patch.object(hotkeys, "keyboard", kb), \
             mock.patch.object(clipboard, "keyboard", kb), \
             mock.patch.object(clipboard, "pyperclip") as clip, \
             mock.patch.object(clipboard, "_press_copy",
                               side_effect=lambda: kb.send("ctrl+c")), \
             mock.patch.object(clipboard.time, "sleep"), \
             mock.patch.object(engine, "paste_text", side_effect=pasted.append), \
             mock.patch.object(engine, "ask_ollama", return_value=answer), \
             mock.patch.object(engine, "log_to_history"), \
             contextlib.redirect_stdout(io.StringIO()):
            kb.is_pressed.return_value = False
            clip.paste.side_effect = ["saved clipboard", line]
            engine.correct_current_line()
        return pasted, kb

    def test_a_good_fix_is_pasted(self):
        pasted, _ = self.fix_line("teh server is down", "The server is down.")
        self.assertEqual(pasted, ["The server is down."])

    def test_the_line_is_selected_then_copied(self):
        """Shift+Home selects back to the start of the line; the copy comes after."""
        _, kb = self.fix_line("teh server is down", "The server is down.")
        sends = [c.args[0] for c in kb.send.call_args_list]
        self.assertIn("shift+home", sends)
        self.assertLess(sends.index("shift+home"), sends.index("ctrl+c"))

    def test_an_answer_in_the_wrong_language_is_not_pasted(self):
        with self.assertLogs(level="WARNING"):
            pasted, _ = self.fix_line("teh server is down", "服务器已关闭")
        self.assertEqual(pasted, [])

    def test_an_unreachable_ai_is_reported(self):
        """The line was quietly deselected, with nothing to say the AI was down."""
        console = io.StringIO()
        with mock.patch.object(engine, "keyboard") as kb, \
             mock.patch.object(hotkeys, "keyboard", kb), \
             mock.patch.object(clipboard, "keyboard", kb), \
             mock.patch.object(clipboard, "pyperclip") as clip, \
             mock.patch.object(clipboard, "_press_copy",
                               side_effect=lambda: kb.send("ctrl+c")), \
             mock.patch.object(clipboard.time, "sleep"), \
             mock.patch.object(engine, "paste_text") as paste, \
             mock.patch.object(engine, "ask_ollama", return_value=None), \
             contextlib.redirect_stdout(console):
            kb.is_pressed.return_value = False
            clip.paste.side_effect = ["saved", "teh line"]
            engine.correct_current_line()
        paste.assert_not_called()
        self.assertIn("AI unavailable", console.getvalue())

    def test_an_arabic_line_must_come_back_arabic(self):
        with self.assertLogs(level="WARNING"):
            pasted, _ = self.fix_line("الخادم معطل", "The server is down.")
        self.assertEqual(pasted, [])

    def test_waits_for_shift_to_be_released_before_copying(self):
        """Ctrl+C sent while you still hold Shift is Ctrl+Shift+C — DevTools in a
        browser, not copy."""
        events = []
        held = iter([True, True])                    # Shift still down for two checks

        def is_pressed(key):
            down = next(held, False)
            events.append(("down" if down else "up", key))
            return down
        with mock.patch.object(engine, "keyboard") as kb, \
             mock.patch.object(hotkeys, "keyboard", kb), \
             mock.patch.object(clipboard, "keyboard", kb), \
             mock.patch.object(clipboard, "pyperclip") as clip, \
             mock.patch.object(clipboard, "_press_copy",
                               side_effect=lambda: kb.send("ctrl+c")), \
             mock.patch.object(clipboard.time, "sleep"), \
             mock.patch.object(engine, "paste_text"), \
             mock.patch.object(engine, "ask_ollama", return_value="Fixed."), \
             mock.patch.object(engine, "log_to_history"), \
             mock.patch.object(engine.time, "sleep"), \
             contextlib.redirect_stdout(io.StringIO()):
            kb.is_pressed.side_effect = is_pressed
            kb.send.side_effect = lambda key: events.append(("send", key))
            clip.paste.side_effect = ["saved", "line"]
            engine.correct_current_line()
        first_send = next(i for i, e in enumerate(events) if e[0] == "send")
        self.assertIn(("up", "shift"), events[:first_send], "sent keys without checking Shift")
        shift_up = events.index(("up", "shift"))
        last_down = max(i for i, e in enumerate(events) if e[0] == "down")
        self.assertLess(last_down, shift_up)         # it kept checking while Shift was held
        self.assertLess(shift_up, first_send)        # and sent nothing until it was up


if __name__ == "__main__":
    unittest.main()
