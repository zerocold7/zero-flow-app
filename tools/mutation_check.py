r"""Prove the tests guard the fixes: break each fix on purpose and require its test to
fail. A test that stays green while the code it guards is broken guards nothing.

    venv\Scripts\python.exe tools\mutation_check.py            (all of them)
    venv\Scripts\python.exe tools\mutation_check.py "ending:"  (labels containing this)

Each entry: (label, unused, exact code, what to replace it with, test to run). The code
is found by its exact text in zeroflow/, reader/ or the entry points, so it must appear
exactly once; after a refactor, update an entry whose text changed (it shows SKIPPED).
Every file is restored afterwards. Run it from the project root, with the venv's Python.
"""
import glob
import shutil
import subprocess
import sys

MUTATIONS = [
    ("openai: key only when set", "x",
     "    headers = {\"Authorization\": f\"Bearer {AI_API_KEY}\"} if AI_API_KEY else {}\n",
     "    headers = {\"Authorization\": f\"Bearer {AI_API_KEY}\"}\n",
     "tests.test_llm.TestOpenAICompatible.test_the_request_is_a_chat_with_the_instruction_as_system"),
    ("openai: empty answer is no answer", "x",
     "    if not output:\n        logging.warning(\"AI server returned an empty answer.\")\n        return None\n", "",
     "tests.test_llm.TestOpenAICompatible.test_no_answer_is_none_with_the_reason_logged"),
    ("openai: unknown provider is reported", "x",
     "    settings.problems.append(f'AI_PROVIDER=", "    (f'AI_PROVIDER=",
     "tests.test_llm.TestChoosingAProvider.test_an_unknown_name_is_reported_and_ollama_used"),
    ("settings: a mistake is recorded", "x",
     "    problems.append(f'{name}=\"{raw}\" in .env is not {wanted} — using {default}.')\n", "",
     "tests.test_settings.TestMistakes.test_a_word_where_a_number_belongs_is_reported_and_the_default_used"),
    ("settings: the range is checked", "x",
     "    if minimum is not None and value < minimum:\n        return _bad(name, raw, f\"{minimum} or more\", default)\n    return value\n\n\ndef choice",
     "    return value\n\n\ndef choice",
     "tests.test_settings.TestMistakes.test_a_number_out_of_range_is_reported"),
    ("settings: start-up reports them", "x",
     "    ui.report_setting_problems(settings.problems, ENABLE_TOASTS)\n", "",
     "tests.test_settings.TestStartUp.test_the_engine_reports_mistakes_when_it_starts"),
    ("copy: clipboard cleared before the copy", "x",
     "            pyperclip.copy(\"\")                   # so a failed copy reads as empty, not as stale text\n", "",
     "tests.test_clipboard.TestCopySelection.test_nothing_selected_gives_none"),
    ("copy: clipboard restored", "x",
     "        finally:\n            pyperclip.copy(saved_clipboard)\n", "        finally:\n            pass\n",
     "tests.test_clipboard.TestCopySelection.test_returns_the_selection_and_restores_the_clipboard"),
    ("copy: waits for a slow app", "x",
     "            for _ in range(POLL_ATTEMPTS):\n", "            for _ in range(1):\n",
     "tests.test_clipboard.TestCopySelection.test_a_slow_app_is_waited_for"),
    ("copy: the line fix selects the line", "x",
     "    target_text = copy_selection(select=\"shift+home\")\n", "    target_text = copy_selection()\n",
     "tests.test_arabic.TestFixLine.test_the_line_is_selected_then_copied"),
    ("ending: quieter than speech means never said", "local_flow.py",
     "        invented = quieter_db >= INVENTED_QUIETER_DB or confidence < INVENTED_MAX_PROBABILITY\n",
     "        invented = confidence < INVENTED_MAX_PROBABILITY\n",
     "tests.test_hallucination.TestInventedEndings.test_thank_you_on_a_breath_is_dropped"),
    ("ending: low confidence means never said", "local_flow.py",
     "        invented = quieter_db >= INVENTED_QUIETER_DB or confidence < INVENTED_MAX_PROBABILITY\n",
     "        invented = quieter_db >= INVENTED_QUIETER_DB\n",
     "tests.test_hallucination.TestInventedEndings.test_an_ending_whisper_was_unsure_of_is_dropped"),
    ("ending: a loud, sure thank you stays", "local_flow.py",
     "        invented = quieter_db >= INVENTED_QUIETER_DB or confidence < INVENTED_MAX_PROBABILITY\n",
     "        invented = True\n",
     "tests.test_hallucination.TestInventedEndings.test_a_clearly_spoken_thank_you_stays"),
    ("ending: alone and quiet is dropped", "local_flow.py",
     "        invented = dbfs < INVENTED_ALONE_MAX_DBFS or confidence < INVENTED_MAX_PROBABILITY\n",
     "        invented = False\n",
     "tests.test_hallucination.TestInventedEndings.test_a_clip_that_is_only_an_invented_phrase_comes_out_empty"),
    ("ending: alone and clear stays", "local_flow.py",
     "        invented = dbfs < INVENTED_ALONE_MAX_DBFS or confidence < INVENTED_MAX_PROBABILITY\n",
     "        invented = True\n",
     "tests.test_hallucination.TestInventedEndings.test_a_clip_that_is_only_a_clear_thank_you_stays"),
    ("ending: only at the very end", "local_flow.py",
     "tuple(t for _, t in flat[-len(phrase):]) == phrase:",
     "phrase[0] in [t for _, t in flat]:",
     "tests.test_hallucination.TestInventedEndings.test_thank_you_in_the_middle_is_never_touched"),
    ("ending: transcription applies the filter", "local_flow.py",
     "        if audio is not None and words:\n", "        if False:\n",
     "tests.test_hallucination.TestTranscribeUsesTheFilter"),
    ("ending: Arabic letters are normalised", "local_flow.py",
     "    for variants, plain in ((\"أإآ\", \"ا\"), (\"ى\", \"ي\"), (\"ة\", \"ه\")):\n        text = re.sub(f\"[{variants}]\", plain, text)\n    return re.sub(",
     "    return re.sub(",
     "tests.test_hallucination.TestInventedEndings.test_arabic_spelling_variants_still_match"),
    ("child dies with the engine (kill on close)", "flow_signals.py",
     "            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE\n",
     "            limits.BasicLimitInformation.LimitFlags = 0\n",
     "tests.test_processes.TestChildDiesWithParent"),
    ("reader crash exits non-zero", "reader/__main__.py",
     "        sys.exit(1)\n", "",
     "tests.test_processes.TestReaderExitCode"),
    ("crashed reader is restarted", "zero_flow.py",
     "        reader_process = spawn_reader()\n", "        return\n",
     "tests.test_processes.TestReaderSupervision.test_a_crashed_reader_is_restarted"),
    ("restarts stop after the limit", "zero_flow.py",
     "        if restarts >= MAX_READER_RESTARTS:", "        if False:",
     "tests.test_processes.TestReaderSupervision.test_it_gives_up_after_repeated_crashes"),
    ("tray exit is not a crash", "zero_flow.py",
     "        if shutting_down or signals.exit_requested():\n", "        if shutting_down:\n",
     "tests.test_processes.TestReaderSupervision.test_exit_from_the_tray_is_not_a_crash"),
    ("shutdown's own stop is not a crash", "zero_flow.py",
     "        if shutting_down or signals.exit_requested():\n", "        if signals.exit_requested():\n",
     "tests.test_processes.TestReaderSupervision.test_the_engine_stopping_the_reader_is_not_a_crash"),
    ("AI context is sent", "flow_core.py",
     "        options[\"num_ctx\"] = OLLAMA_NUM_CTX\n", "        pass\n",
     "tests.test_arabic.TestOllamaRequest.test_the_context_is_sized_for_dictation"),
    ("warm-up uses the same options", "flow_core.py",
     "                                                        \"options\": _ollama_options()},\n",
     "                                                        },\n",
     "tests.test_arabic.TestOllamaRequest.test_warm_up_loads_the_model_exactly_as_requests_will_use_it"),
    ("context 0 keeps the model's own", "flow_core.py",
     "    if OLLAMA_NUM_CTX > 0:\n", "    if True:\n",
     "tests.test_arabic.TestOllamaRequest.test_a_context_of_zero_keeps_the_models_own"),
    ("standalone reader exit spares the engine", "reader/app.py",
     "    if CHILD_MODE:\n        signals.request_exit()", "    if True:\n        signals.request_exit()",
     "tests.test_processes.TestReaderExitButton.test_a_standalone_reader_does_not_shut_down_the_engine"),
    ("second claim is refused", "flow_signals.py",
     "    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:", "    if False:",
     "tests.test_processes.TestSingleInstance.test_another_process_is_refused_while_this_one_holds_it"),
    ("engine checks the claim before loading", "zero_flow.py",
     "    if not (signals.claim_single_instance(\"dictation\")", "    if False and (signals.claim_single_instance(\"dictation\")",
     "tests.test_processes.TestSecondCopyStopsAtTheDoor.test_the_whole_engine"),
    ("dictation half checks the claim", "local_flow.py",
     "    if not signals.claim_single_instance(\"dictation\"):", "    if False:",
     "tests.test_processes.TestSecondCopyStopsAtTheDoor.test_the_dictation_half_alone"),
    ("crashes are logged", "flow_core.py",
     "    _log_crashes(component)\n", "",
     "tests.test_processes.TestCrashLogging"),
    ("GPU failure retries on the CPU", "local_flow.py",
     "        return run(cpu_fallback_model())\n", "        return None, None\n",
     "tests.test_transcribe.TestGpuOutOfMemory.test_the_clip_is_transcribed_on_the_cpu_instead"),
    ("CPU copy is loaded once", "local_flow.py",
     "    if _cpu_model is None:\n        _cpu_model = WhisperModel(",
     "    if True:\n        _cpu_model = WhisperModel(",
     "tests.test_transcribe.TestGpuOutOfMemory.test_the_cpu_model_is_loaded_once"),
    ("a failure is not logged as silence", "local_flow.py",
     "    if text is None:\n        logging.info(\"Transcription failed",
     "    if False:\n        logging.info(\"Transcription failed",
     "tests.test_transcribe.TestFailureIsNotCalledSilence.test_a_failed_transcription_is_logged_as_a_failure"),
    ("history is capped on every write", "local_flow.py",
     "        logging.error(f\"History write fail: {e}\")\n    cap_history_file()\n",
     "        logging.error(f\"History write fail: {e}\")\n",
     "tests.test_history.TestHistoryCap.test_the_cap_holds_while_the_engine_runs"),
    ("history trims at an entry boundary", "local_flow.py",
     "        kept = tail[start.start():] if start else \"\"\n", "        kept = tail\n",
     "tests.test_history.TestHistoryCap.test_trimming_keeps_whole_entries"),
    ("Esc really cancels", "local_flow.py",
     "        capture.stop(cancel=True)\n        ui.set_tray_state(False)\n",
     "        capture.stop()\n        ui.set_tray_state(False)\n",
     "tests.test_capture.TestCancel.test_a_cancelled_clip_stays_cancelled_when_the_next_starts"),
    ("an old capture cannot end the new one", "local_flow.py",
     "        if current_capture is capture:\n            current_capture = None\n",
     "        current_capture = None\n",
     "tests.test_capture.TestMicrophoneError.test_a_failed_microphone_does_not_stop_the_next_recording"),
    ("each capture keeps its own audio", "local_flow.py",
     "        self._chunks = []\n",
     "        self._chunks = globals().setdefault('_SHARED_CHUNKS', [])\n",
     "tests.test_capture.TestBackToBack.test_stop_then_start_keeps_the_two_clips_apart"),
    ("recording stops at the maximum length", "local_flow.py",
     "            if not capture.stopped.wait(MAX_RECORDING_SECONDS):",
     "            if not capture.stopped.wait():",
     "tests.test_capture.TestMaximumLength.test_a_forgotten_recording_stops_by_itself"),
    ("warm-up checks the HTTP status", "flow_core.py",
     "    if response.status_code == 200:\n        logging.info(f\"LLM '{model}' loaded ahead",
     "    if True:\n        logging.info(f\"LLM '{model}' loaded ahead",
     "tests.test_arabic.TestOllamaRequest.test_warm_up_reports_a_model_ollama_does_not_have"),
    ("fallback model is not cached", "flow_core.py",
     "        if not settled:\n            return name\n", "",
     "tests.test_arabic.TestModelDiscovery.test_the_fallback_is_not_kept_once_ollama_is_running"),
    ("empty answer is no answer", "flow_core.py",
     "            if not output:\n                logging.warning(\"Ollama returned an empty answer.\")\n                return None\n", "",
     "tests.test_arabic.TestOllamaRequest.test_an_empty_answer_counts_as_no_answer"),
    ("unreachable AI is not called Polished", "local_flow.py",
     "        answer = ask_ai(text, context, prompt)\n        if answer is None:\n            return _ai_unavailable(text)\n",
     "        answer = ask_ai(text, context, prompt) or text\n",
     "tests.test_arabic.TestArabicPolish.test_an_unreachable_ai_is_reported_not_called_polished"),
    ("unreachable AI is not called Translated", "local_flow.py",
     "        answer = ask_ai(text, None, prompt)\n        if answer is None:\n            return _ai_unavailable(text)\n",
     "        answer = ask_ai(text, None, prompt) or text\n",
     "tests.test_arabic.TestTranslation.test_an_unreachable_ai_is_reported_not_called_translated"),
    ("line fix goes through the language guard", "local_flow.py",
     "        fixed = checked_ai_output(fixed, target_text, lang)\n", "        pass\n",
     "tests.test_arabic.TestFixLine.test_an_answer_in_the_wrong_language_is_not_pasted"),
    ("line fix waits for Shift", "local_flow.py",
     "    wait_for_release(HOTKEYS[\"fix\"])\n", "",
     "tests.test_arabic.TestFixLine.test_waits_for_shift_to_be_released_before_copying"),
    ("chatter is filtered from Shift+F1", "local_flow.py",
     "if term and not term.endswith(\":\") and len(term.split()) <= MAX_TERM_WORDS:",
     "if term:",
     "tests.test_vocabulary.TestMemoryMaintenance.test_the_models_chatter_is_not_kept_as_vocabulary"),
    ("learning waits for the vocabulary lock", "flow_core.py",
     "        with VOCAB_LOCK:\n            learned = word not in load_vocabulary()\n            if learned:\n                append_vocabulary_word(word)\n",
     "        learned = word not in load_vocabulary()\n        if learned:\n            append_vocabulary_word(word)\n",
     "tests.test_vocabulary.TestSafeAppend.test_writers_wait_for_the_vocabulary_lock"),
]

only = sys.argv[1] if len(sys.argv) > 1 else ""
failed = 0
for label, path, old, new, test in MUTATIONS:
    if only and only not in label:
        continue
    homes = [f for f in glob.glob("zeroflow/**/*.py", recursive=True) + glob.glob("reader/*.py")
             + ["local_flow.py", "zero_flow.py"]
             if open(f, encoding="utf-8").read().count(old) == 1]
    if len(homes) != 1:
        print(f"SKIPPED  {label}: anchor found in {homes or 'no file'}")
        failed += 1
        continue
    path = homes[0]
    shutil.copyfile(path, path + ".mutbak")
    try:
        src = open(path, encoding="utf-8").read()
        if src.count(old) != 1:
            print(f"SKIPPED  {label}: anchor found {src.count(old)} times")
            failed += 1
            continue
        open(path, "w", encoding="utf-8").write(src.replace(old, new))
        run = subprocess.run([sys.executable, "-m", "unittest", test],
                             capture_output=True, text=True, timeout=120)
        caught = run.returncode != 0 and ("FAIL:" in run.stderr or "AssertionError" in run.stderr)
        print(f"{'CAUGHT ' if caught else 'MISSED '}  {label}")
        failed += not caught
    finally:
        shutil.move(path + ".mutbak", path)
print("all caught" if not failed else f"{failed} not caught")
sys.exit(1 if failed else 0)
