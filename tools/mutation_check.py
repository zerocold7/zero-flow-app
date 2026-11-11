r"""Prove the tests guard the fixes: break each fix on purpose and require its test to
fail. A test that stays green while the code it guards is broken guards nothing.

    venv\Scripts\python.exe tools\mutation_check.py            (all of them)
    venv\Scripts\python.exe tools\mutation_check.py "ending:"  (labels containing this)

Each entry: (label, exact code, what to replace it with, test to run). The code
is found by its exact text in zeroflow/, reader/ or the entry points, so it must appear
exactly once; after a refactor, update an entry whose text changed (it shows SKIPPED).
Every file is restored afterwards. Run it from the project root, with the venv's Python.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

MUTATIONS = [
    ('claude: a refusal is no answer', '    if response.stop_reason == "refusal":\n', '    if False:\n', 'tests.test_claude_provider.TestNoAnswer.test_a_refusal_is_no_answer'),
    ('claude: the refusal fallback is on', '            fallbacks="default",\n', '', 'tests.test_claude_provider.TestRequest.test_quick_clean_up_settings_for_the_current_model'),
    ('claude: a rejected key is named', '        return _no_answer("the API key was rejected (401)", "The API key was rejected.")\n', '        return _no_answer("rejected (401)", "Rejected.")\n', 'tests.test_claude_provider.TestNoAnswer.test_a_rejected_key_says_so'),
    ('runtime: checksum is checked', '            if actual != expected:\n', '            if False:\n', 'tests.test_llama_runtime.TestInstall.test_a_wrong_checksum_is_refused_and_nothing_installed'),
    ('runtime: nothing written outside its folder', '            if not (target == root or target.startswith(root + os.sep)):\n', '            if False:\n', 'tests.test_llama_runtime.TestInstall.test_an_archive_that_writes_outside_its_folder_is_refused'),
    ('runtime: an AMD/Intel card gets vulkan', '    if any(dedicated and vendor in ("amd", "intel") for vendor, dedicated in kinds):\n', '    if False:\n', 'tests.test_llama_runtime.TestVariants.test_the_build_follows_the_graphics_card'),
    ('builtin: thinking off', '            "--reasoning", "off",             # thinking made Polish 2.4-7.8 s, not 0.26 s\n', '', 'tests.test_builtin_ai.TestStartingTheServer.test_it_runs_with_thinking_off_and_the_set_context'),
    ('builtin: cpu build stays off the card', '            "-ngl", "0" if variant == "cpu" else "99",', '            "-ngl", "99",', 'tests.test_builtin_ai.TestStartingTheServer.test_the_cpu_build_keeps_the_model_off_the_graphics_card'),
    ('builtin: tied to the engine', '    signals.bind_child_to_this_process(_process)\n', '', 'tests.test_builtin_ai.TestStartingTheServer.test_the_server_is_tied_to_the_engine'),
    ('builtin: a running server is shared', 'def _start() -> bool:\n    global _process\n    if _healthy():\n        return True\n', 'def _start() -> bool:\n    global _process\n', 'tests.test_builtin_ai.TestSharing.test_a_server_already_running_is_used_not_started_again'),
    ('builtin: waits until ready', '        if _healthy():\n            logging.info(f"Built-in AI ready', '        if True:\n            logging.info(f"Built-in AI ready', 'tests.test_builtin_ai.TestStartingTheServer.test_start_returns_only_once_the_server_answers'),
    ('builtin: missing runtime falls back to ollama', '    if name == "builtin" and not builtin.available():\n', '    if False:\n', 'tests.test_builtin_ai.TestChoosingTheBuiltinProvider.test_without_its_runtime_ollama_is_used_and_the_fix_named'),
    ('openai: key only when set', '    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}\n', '    headers = {"Authorization": f"Bearer {api_key}"}\n', 'tests.test_llm.TestOpenAICompatible.test_the_request_is_a_chat_with_the_instruction_as_system'),
    ('ai: an empty answer is no answer', '    if not answer.strip():\n        logging.warning("The AI returned an empty answer.")\n        return None\n', '', 'tests.test_llm.TestRouting.test_an_empty_answer_is_no_answer_and_says_why'),
    ("ai: every provider's answer can teach a word", '    return absorb_learned_word(answer.strip(), heard=raw_text) or None\n', '    return answer.strip()\n', 'tests.test_llm.TestRouting.test_learned_words_are_taken_from_any_providers_answer'),
    ('ai: the spinner stops even on a failure', '    finally:\n        ui.stop_processing_spinner()\n', '', 'tests.test_llm.TestRouting.test_the_spinner_stops_even_if_the_provider_fails'),
    ('ai: a failing provider is no answer', '        answer = None\n    finally:\n', '        raise\n    finally:\n', 'tests.test_llm.TestRouting.test_a_failing_provider_is_no_answer_and_says_why'),
    ('openai: unknown provider is reported', "    settings.problems.append(f'AI_PROVIDER=", "    (f'AI_PROVIDER=", 'tests.test_llm.TestChoosingAProvider.test_an_unknown_name_is_reported_and_ollama_used'),
    ('settings: a mistake is recorded', '    problems.append(f\'{name}="{raw}" in {_where} is not {wanted} — using {default}.\')\n', '', 'tests.test_settings.TestMistakes.test_a_word_where_a_number_belongs_is_reported_and_the_default_used'),
    ('settings: the range is checked', '    if minimum is not None and value < minimum:\n        return _bad(name, raw, f"{minimum} or more", default)\n    if maximum', '    if maximum', 'tests.test_settings.TestMistakes.test_a_number_out_of_range_is_reported'),
    ('settings: the maximum is checked', '    if maximum is not None and value > maximum:\n', '    if False:\n', 'tests.test_settings.TestSafeguards.test_a_number_above_its_maximum_is_reported'),
    ('settings: a key used twice is reported', '        if other != name:\n', '        if False:\n', 'tests.test_settings.TestSafeguards.test_one_key_for_two_actions_is_reported_by_name'),
    ('settings: a key over plain http is caught', '    return bool(api_key) and address.scheme == "http" and not _this_pc(address.hostname)\n', '    return False\n', 'tests.test_settings.TestSafeguards.test_a_key_over_plain_http_to_another_computer_is_caught'),
    ('settings: start-up reports them', '    ui.report_setting_problems(settings.problems, ENABLE_TOASTS)\n', '', 'tests.test_settings.TestStartUp.test_the_engine_reports_mistakes_when_it_starts'),
    ('copy: clipboard cleared before the copy', '            system_clipboard.clear()             # so a failed copy reads as empty, not as stale text\n', '', 'tests.test_clipboard.TestCopySelection.test_nothing_selected_gives_none'),
    ('copy: clipboard restored', '            return None\n        finally:\n            _restore(saved_clipboard)\n', '            return None\n        finally:\n            pass\n', 'tests.test_clipboard.TestCopySelection.test_returns_the_selection_and_restores_the_clipboard'),
    ('paste: clipboard restored on a failure', '        finally:\n            # Even when a step above fails', '        except BaseException:\n            raise\n        else:\n            # Even when a step above fails', 'tests.test_clipboard.TestPaste.test_the_clipboard_is_restored_even_if_the_paste_fails'),
    ('copy: waits for a slow app', '            for _ in range(POLL_ATTEMPTS):\n', '            for _ in range(1):\n', 'tests.test_clipboard.TestCopySelection.test_a_slow_app_is_waited_for'),
    ('copy: the line fix selects the line', '    target_text = copy_selection(select="shift+home")\n', '    target_text = copy_selection()\n', 'tests.test_arabic.TestFixLine.test_the_line_is_selected_then_copied'),
    ('ending: quieter than speech means never said', '        invented = quieter_db >= INVENTED_QUIETER_DB or confidence < INVENTED_MAX_PROBABILITY\n', '        invented = confidence < INVENTED_MAX_PROBABILITY\n', 'tests.test_hallucination.TestInventedEndings.test_thank_you_on_a_breath_is_dropped'),
    ('ending: low confidence means never said', '        invented = quieter_db >= INVENTED_QUIETER_DB or confidence < INVENTED_MAX_PROBABILITY\n', '        invented = quieter_db >= INVENTED_QUIETER_DB\n', 'tests.test_hallucination.TestInventedEndings.test_an_ending_whisper_was_unsure_of_is_dropped'),
    ('ending: a loud, sure thank you stays', '        invented = quieter_db >= INVENTED_QUIETER_DB or confidence < INVENTED_MAX_PROBABILITY\n', '        invented = True\n', 'tests.test_hallucination.TestInventedEndings.test_a_clearly_spoken_thank_you_stays'),
    ('ending: alone and quiet is dropped', '        invented = dbfs < INVENTED_ALONE_MAX_DBFS or confidence < INVENTED_MAX_PROBABILITY\n', '        invented = False\n', 'tests.test_hallucination.TestInventedEndings.test_a_clip_that_is_only_an_invented_phrase_comes_out_empty'),
    ('ending: alone and clear stays', '        invented = dbfs < INVENTED_ALONE_MAX_DBFS or confidence < INVENTED_MAX_PROBABILITY\n', '        invented = True\n', 'tests.test_hallucination.TestInventedEndings.test_a_clip_that_is_only_a_clear_thank_you_stays'),
    ('ending: only at the very end', 'tuple(t for _, t in flat[-len(phrase):]) == phrase:', 'phrase[0] in [t for _, t in flat]:', 'tests.test_hallucination.TestInventedEndings.test_thank_you_in_the_middle_is_never_touched'),
    ('ending: transcription applies the filter', '        if recorded is not None and words:\n', '        if False:\n', 'tests.test_hallucination.TestTranscribeUsesTheFilter'),
    ('ending: Arabic letters are normalised', '    for variants, plain in (("أإآ", "ا"), ("ى", "ي"), ("ة", "ه")):\n        text = re.sub(f"[{variants}]", plain, text)\n    return re.sub(', '    return re.sub(', 'tests.test_hallucination.TestInventedEndings.test_arabic_spelling_variants_still_match'),
    ('child dies with the engine (kill on close)', '            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE\n', '            limits.BasicLimitInformation.LimitFlags = 0\n', 'tests.test_processes.TestChildDiesWithParent'),
    ('reader crash exits non-zero', '        sys.exit(1)\n', '', 'tests.test_processes.TestReaderExitCode'),
    ('crashed reader is restarted', '        time.sleep(delay)\n        reader_process = spawn_reader()\n', '        time.sleep(delay)\n        return\n', 'tests.test_processes.TestReaderSupervision.test_a_crashed_reader_is_restarted'),
    ('restarts stop after the limit', '        if restarts >= MAX_READER_RESTARTS:', '        if False:', 'tests.test_processes.TestReaderSupervision.test_it_gives_up_after_repeated_crashes'),
    ('tray exit is not a crash', '        if shutting_down or not reader_wanted or signals.exit_requested():\n', '        if shutting_down or not reader_wanted:\n', 'tests.test_processes.TestReaderSupervision.test_exit_from_the_tray_is_not_a_crash'),
    ("shutdown's own stop is not a crash", '        if shutting_down or not reader_wanted or signals.exit_requested():\n', '        if not reader_wanted or signals.exit_requested():\n', 'tests.test_processes.TestReaderSupervision.test_the_engine_stopping_the_reader_is_not_a_crash'),
    ('AI context is sent', '        options["num_ctx"] = OLLAMA_NUM_CTX\n', '        pass\n', 'tests.test_arabic.TestOllamaRequest.test_the_context_is_sized_for_dictation'),
    ('warm-up uses the same options', '                                                        "options": _ollama_options()},\n', '                                                        },\n', 'tests.test_arabic.TestOllamaRequest.test_warm_up_loads_the_model_exactly_as_requests_will_use_it'),
    ("context 0 keeps the model's own", '    if OLLAMA_NUM_CTX > 0:\n', '    if True:\n', 'tests.test_arabic.TestOllamaRequest.test_a_context_of_zero_keeps_the_models_own'),
    ('second claim is refused', '        if ctypes.get_last_error() != ERROR_ALREADY_EXISTS:\n', '        if True:\n', 'tests.test_processes.TestSingleInstance.test_another_process_is_refused_while_this_one_holds_it'),
    ('engine checks the claim before loading', '    if not (signals.claim_single_instance("dictation", wait)', '    if False and (signals.claim_single_instance("dictation", wait)', 'tests.test_processes.TestSecondCopyStopsAtTheDoor.test_the_whole_engine'),
    ('crashes are logged', '    _log_crashes(component)\n', '', 'tests.test_processes.TestCrashLogging'),
    ('GPU failure retries on the CPU', '        return run(cpu_fallback_model())\n', '        return None, None\n', 'tests.test_transcribe.TestGpuOutOfMemory.test_the_clip_is_transcribed_on_the_cpu_instead'),
    ('CPU copy is loaded once', '    if _cpu_model is None:\n        _cpu_model = WhisperModel(', '    if True:\n        _cpu_model = WhisperModel(', 'tests.test_transcribe.TestGpuOutOfMemory.test_the_cpu_model_is_loaded_once'),
    ('a failure is not logged as silence', '    if text is None:\n        logging.info("Transcription failed', '    if False:\n        logging.info("Transcription failed', 'tests.test_transcribe.TestFailureIsNotCalledSilence.test_a_failed_transcription_is_logged_as_a_failure'),
    ('history is capped on every write', '            logging.error(f"History write fail: {e}")\n        cap_history_file()\n', '            logging.error(f"History write fail: {e}")\n', 'tests.test_history.TestHistoryCap.test_the_cap_holds_while_the_engine_runs'),
    ('history trims at an entry boundary', '        kept = tail[start.start():] if start else ""\n', '        kept = tail\n', 'tests.test_history.TestHistoryCap.test_trimming_keeps_whole_entries'),
    ('Esc really cancels', '        capture.stop(cancel=True)\n        ui.set_tray_state(False)\n', '        capture.stop()\n        ui.set_tray_state(False)\n', 'tests.test_capture.TestCancel.test_a_cancelled_clip_stays_cancelled_when_the_next_starts'),
    ('an old capture cannot end the new one', '        if current_capture is capture:\n            current_capture = None\n', '        current_capture = None\n', 'tests.test_capture.TestMicrophoneError.test_a_failed_microphone_does_not_stop_the_next_recording'),
    ('each capture keeps its own audio', '        self._chunks = []\n', "        self._chunks = globals().setdefault('_SHARED_CHUNKS', [])\n", 'tests.test_capture.TestBackToBack.test_stop_then_start_keeps_the_two_clips_apart'),
    ('recording stops at the maximum length', '            if not capture.stopped.wait(MAX_RECORDING_SECONDS):', '            if not capture.stopped.wait():', 'tests.test_capture.TestMaximumLength.test_a_forgotten_recording_stops_by_itself'),
    ('warm-up checks the HTTP status', '    if response.status_code == 200:\n        logging.info(f"LLM \'{model}\' loaded ahead', '    if True:\n        logging.info(f"LLM \'{model}\' loaded ahead', 'tests.test_arabic.TestOllamaRequest.test_warm_up_reports_a_model_ollama_does_not_have'),
    ('fallback model is not cached', '        if not settled:\n            return name\n', '', 'tests.test_arabic.TestModelDiscovery.test_ollama_down_gives_no_name_and_it_is_not_kept'),
    ('whisper hears the clip at full scale', '    if peak > 0:\n        clip = clip / peak\n', '', 'tests.test_transcribe.TestWhatWhisperHears'),
    ('unreachable AI is not called Polished', '        answer = ask_ai(text, context, prompt, learn=cfg["lang"] == "en")\n        if answer is None:\n            return _ai_unavailable(text)\n', '        answer = ask_ai(text, context, prompt, learn=cfg["lang"] == "en") or text\n', 'tests.test_arabic.TestArabicPolish.test_an_unreachable_ai_is_reported_not_called_polished'),
    ('unreachable AI is not called Translated', '        answer = ask_ai(text, None, prompt)\n        if answer is None:\n            return _ai_unavailable(text)\n', '        answer = ask_ai(text, None, prompt) or text\n', 'tests.test_arabic.TestTranslation.test_an_unreachable_ai_is_reported_not_called_translated'),
    ('line fix goes through the language guard', '        fixed = checked_ai_output(fixed, target_text, lang)\n', '        pass\n', 'tests.test_arabic.TestFixLine.test_an_answer_in_the_wrong_language_is_not_pasted'),
    ('line fix waits for Shift', '    wait_for_release(HOTKEYS["fix"])\n', '', 'tests.test_arabic.TestFixLine.test_waits_for_shift_to_be_released_before_copying'),
    ('chatter is filtered from Shift+F1', 'if (term and not term.endswith(":") and len(term.split()) <= MAX_TERM_WORDS', 'if (term', 'tests.test_vocabulary.TestMemoryMaintenance.test_the_models_chatter_is_not_kept_as_vocabulary'),
    ('learning waits for the vocabulary lock', '        with VOCAB_LOCK:\n            learned = word not in load_vocabulary()\n            if learned:\n                append_vocabulary_word(word)\n', '        learned = word not in load_vocabulary()\n        if learned:\n            append_vocabulary_word(word)\n', 'tests.test_vocabulary.TestSafeAppend.test_writers_wait_for_the_vocabulary_lock'),
    ('unload: the built-in AI really stops', '        running = _process is not None and _process.poll() is None\n        stop()\n', '        running = _process is not None and _process.poll() is None\n', 'tests.test_unload_ai.TestBuiltinUnload.test_unloading_stops_the_server_and_the_next_request_loads_it_again'),
    ('unload: Ollama is told to drop it now', 'json={"model": model, "keep_alive": 0}', 'json={"model": model, "keep_alive": OLLAMA_KEEP_ALIVE}', 'tests.test_unload_ai.TestOllamaUnload.test_ollama_is_told_to_drop_the_model_now'),
    ('unload: AI_LOAD_AT_START=False is honoured', '    if AI_LOAD_AT_START:\n', '    if True:\n', 'tests.test_unload_ai.TestTheEngine.test_ai_load_at_start_false_leaves_it_for_the_first_polish'),
    ('unload: the engine hears the tray', '    threading.Thread(target=watch_for_unload_requests, daemon=True).start()\n', '', 'tests.test_unload_ai.TestTheEngine.test_the_engine_listens_for_unload_requests'),
    ('log: dictated words kept out of the log', '    if LOG_DICTATION_TEXT:\n        return DICTATED_MARK', '    if True:\n        return DICTATED_MARK', 'tests.test_log_privacy.TestDictationIsNotLogged.test_the_words_are_not_in_the_log'),
    ('polish: clipboard context only where allowed', '    if MODES[mode]["op"] != "polish" or not SEND_CLIPBOARD_CONTEXT:', '    if MODES[mode]["op"] != "polish":', 'tests.test_clipboard_context.TestPolishReadsTheClipboardOnlyWhenAllowed.test_not_allowed'),
    ('commands: taken from what was said, before the AI', '    text, lead = take_commands(text)\n', '    lead = None\n', 'tests.test_commands_from_speech.TestYourCommandStillWorks.test_new_line_you_said_survives_polish'),
    ('models: Whisper at its pinned revision', 'revision=models.revision(repo),', 'revision=None,', 'tests.test_model_revisions.TestWhisper.test_a_short_name_is_fetched_at_its_pinned_revision'),
    ('reader: one read at a time', '    if not reading.acquire(blocking=False):', '    if not (reading.acquire(blocking=False) or True):', 'tests.test_reader_presses.TestTwoPresses.test_a_press_during_a_read_starts_no_second_one'),
    ('claude: a missing package is named', '    if name == "claude" and not claude.available():', '    if False:', 'tests.test_llm.TestChoosingAProvider.test_claude_without_its_package_is_reported_and_the_builtin_ai_used'),
    ('review: a busy clipboard is restored later', '        threading.Thread(target=_restore_later, args=(saved,), daemon=True).start()\n', '', 'tests.test_review_findings.Finding1ClipboardBusyAfterThePaste.test_the_paste_still_counts_and_the_clipboard_is_restored_later'),
    ('review: Shift+F3 waits for the dictation', '    with processing_lock:\n        _correct_current_line()\n', '    _correct_current_line()\n', 'tests.test_review_findings.Finding2FixLineWaitsForTheDictation.test_shift_f3_does_not_start_while_a_clip_is_processed'),
    ('review: no read into an open microphone', '        if signals.is_recording() or generation != voice_engine.current_generation():', '        if False:', 'tests.test_review_findings.Finding3TheReaderStaysQuietOnceTheMicOpens.test_dictation_starting_while_the_text_is_cleaned_stops_the_read'),
    ('review: only English Polish learns words', '    if not learn:', '    if False:', 'tests.test_review_findings.Finding6OnlyEnglishPolishLearnsWords.test_other_calls_strip_the_tag_and_learn_nothing'),
    ('review: an unknown key falls back', '        keyboard.parse_hotkey(raw)\n', '        pass\n', 'tests.test_review_findings.Finding8AWrongKeyIsReportedNotFatal.test_an_unknown_key_takes_the_default'),
    ('review: our own slow AI server is waited for', '        return _wait_until_ready("still loading")\n', '        pass\n', 'tests.test_review_findings.Finding11OurOwnSlowServerIsWaitedFor.test_a_running_server_that_is_slow_to_answer_is_not_started_twice'),
    ('stability: another Python is named', '    if running == TESTED_PYTHON:\n        return None\n', '', 'tests.test_hardware.TestPythonVersion.test_the_engine_says_so_at_start_up'),
    ('stability: temporary log folders removed', '    atexit.register(_remove_log_dir, folder)\n', '', 'tests.test_temp_logs.TestTemporaryLogFolder.test_the_folder_is_removed_when_the_process_ends'),
    ('stability: a long first sentence is split', '    sentences[:1] = _split_long_first(sentences[0], first_max)\n', '', 'tests.test_batching.TestLongFirstSentence.test_a_long_first_sentence_is_split_at_a_comma'),
    ('cases: Shift+F2 removes the log backups', '            os.remove(LOG_FILE + suffix)\n', '            pass\n', 'tests.test_engine_cases.TestClearLogsAndHistory.test_history_log_and_backups_are_cleared'),
    ('cases: a too-short clip is dropped', '    if len(audio) / SAMPLE_RATE < MIN_CLIP_SECONDS:', '    if False:', 'tests.test_engine_cases.TestOneRecording.test_a_clip_shorter_than_the_minimum_is_dropped'),
    ('cases: a forgotten recording stops itself', '                capture.stop()\n                logging.info(f"Recording reached', '                logging.info(f"Recording reached', 'tests.test_engine_cases.TestOneRecording.test_a_forgotten_recording_stops_by_itself_and_is_kept'),
    ('cases: Esc reaches the app', '    _bound.append(keyboard.add_hotkey(HOTKEYS["panic"], on_cancel_hotkey))', '    _bound.append(keyboard.add_hotkey(HOTKEYS["panic"], on_cancel_hotkey, suppress=True))', 'tests.test_engine_cases.TestKeysAndStart.test_every_key_is_bound_and_only_esc_reaches_the_app'),
    ('cases: a stuck reader is killed at shutdown', '                reader_process.kill()\n', '                pass\n', 'tests.test_supervisor_lifecycle.TestShutdown.test_a_reader_that_does_not_stop_is_killed'),
    ('cases: Smart clean falls back on an echo', '    if not output or output.strip() == prepared.strip():', '    if not output:', 'tests.test_reader_cases.TestSmartCleaning.test_the_text_handed_back_unchanged_falls_back_too'),
    ('live test: a subtitle phrase on real speech is dropped', '    if phrase in SUBTITLE_ENDINGS:', '    if False:', 'tests.test_hallucination.TestInventedEndings.test_the_live_case_subscribe_on_real_speech_is_dropped'),
    ('live test: a cached Whisper folder missing a file is completed', '    if missing := missing_whisper_files(folder):\n', '    if False:\n', 'tests.test_model_revisions.TestWhisper.test_a_cached_folder_missing_a_file_is_completed'),
    ('whisper: an empty file counts as missing', '        if not any(os.path.getsize(path) > 0 for path in found):\n', '        if not found:\n', 'tests.test_model_revisions.TestWhisper.test_an_empty_file_counts_as_missing'),
    ('storage: migrates only without a settings file', '    if os.path.exists(target):\n        return result\n', '', 'tests.test_storage.TestWhenItRuns.test_it_runs_only_when_there_is_no_settings_file'),
    ('storage: the settings file is written last', '    key = values.pop(KEY_NAME, "")\n', '    key = values.pop(KEY_NAME, "")\n    save(target, values)\n', 'tests.test_storage.TestWhenItRuns.test_a_failed_copy_leaves_no_settings_file_so_the_next_start_tries_again'),
    ('storage: the old vocabulary and history are copied', '            _copy(source, os.path.join(data_dir, new))\n', '            pass\n', 'tests.test_storage.TestWhenItRuns.test_the_vocabulary_and_history_are_copied_under_their_new_names'),
    ('storage: the key is taken out of the settings', '    key = values.pop(KEY_NAME, "")\n', '    key = values.get(KEY_NAME, "")\n', 'tests.test_storage.TestApiKey.test_the_key_is_never_written_to_any_file_in_the_data_folder'),
    ('storage: the settings file refuses a key', '    if KEY_NAME in values:\n', '    if False:\n', 'tests.test_storage.TestTheFileItself.test_saving_a_key_into_the_file_is_refused'),
    ('storage: the key goes to Credential Manager', '            keys.set(address, key)\n', '', 'tests.test_storage.TestApiKey.test_the_key_goes_to_credential_manager_under_the_provider_address'),
    ('credentials: a key is stored under the server, not the path', '    return f"{scheme}://{(parts.hostname or \'\').lower()}{shown_port}"\n', '    return url\n', 'tests.test_storage.TestApiKey.test_the_address_is_the_server_not_the_path'),
    ('storage: Remove it deletes only the key line', '    kept = [line for line in lines if not _KEY_LINE.match(line)]\n', '    kept = [line for line in lines if b"AI_" not in line]\n', 'tests.test_storage.TestApiKey.test_remove_it_deletes_only_the_key_line'),
    ('settings: the first start migrates', 'if _migrating:\n    _first_start_migration()\n', '', 'tests.test_storage.TestTheEngineStart.test_the_first_start_migrates_and_runs_on_the_old_values'),
    ('settings: .env is not read once there is a settings file', 'if _migrating:\n    _VALUES, _where = storage.read_env(', 'if True:\n    _VALUES, _where = storage.read_env(', 'tests.test_storage.TestTheEngineStart.test_the_next_start_reads_only_the_settings_file'),
    ('settings: a failed migration stops the engine', '    except Exception as e:\n        raise RuntimeError(', '    except Exception as e:\n        return\n        raise RuntimeError(', 'tests.test_storage.TestAFailedFirstStart.test_the_engine_stops_and_says_why'),
    ('settings: Hugging Face uses the models folder', 'storage.apply_models_dir({"MODELS_DIR": MODELS_DIR}, os.environ)\n', '', 'tests.test_storage.TestTheEngineStart.test_hugging_face_looks_in_the_models_folder'),
    ('overlay: a tooltip-type window is never activated', 'super().__init__(None, Qt.ToolTip |', 'super().__init__(None, Qt.Tool |', 'tests/test_window_overlay.py::test_showing_a_state_never_moves_focus'),
    ('overlay: it does not accept focus', '                         | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)', '                         | Qt.WindowTransparentForInput)', 'tests/test_window_overlay.py::test_it_is_a_tool_window_that_stays_on_top_and_ignores_input'),
    ('overlay: it is shown without activating', '        self.setAttribute(Qt.WA_ShowWithoutActivating)\n', '', 'tests/test_window_overlay.py::test_it_is_a_tool_window_that_stays_on_top_and_ignores_input'),
    ('overlay: clicks pass through', 'Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)', 'Qt.WindowDoesNotAcceptFocus)', 'tests/test_window_overlay.py::test_the_real_window_is_not_activated_passes_clicks_and_stays_on_top'),
    ('overlay: stays on top', 'Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint\n', 'Qt.FramelessWindowHint\n', 'tests/test_window_overlay.py::test_it_is_a_tool_window_that_stays_on_top_and_ignores_input'),
    ('overlay: workers reach it through signals', '    status = Signal(str)          # one of STATES\n', '    status = None\n', 'tests/test_window_overlay.py::test_a_worker_thread_reaches_it_only_through_a_signal'),
    ('key: it is never written to the settings file', '    storage.update(settings_path, {"AI_PROVIDER": provider, "AI_URL": url, "AI_MODEL": model})\n', '    storage.update(settings_path, {"AI_PROVIDER": provider, "AI_URL": url, "AI_MODEL": model, "AI_API_KEY": key or ""})\n', 'tests/test_window_provider.py::test_the_key_is_in_no_part_of_the_settings_file'),
    ('key: it goes to Credential Manager', '            if key:\n                store.set(address, key)\n', '            if False:\n                store.set(address, key)\n', 'tests/test_window_provider.py::test_the_key_goes_to_credential_manager_under_the_address'),
    ('key: a blank key keeps the saved one', '            if key:\n                store.set(address, key)\n            elif clear_key:', "            if True:\n                store.set(address, key or '')\n            elif clear_key:", 'tests/test_window_provider.py::test_a_blank_key_keeps_the_saved_one'),
    ('key: clearing deletes it', '            elif clear_key:\n                store.delete(address)\n', '            elif False:\n                store.delete(address)\n', 'tests/test_window_provider.py::test_clearing_the_key_deletes_it'),
    ('key: nothing is saved for a provider that takes no key', '    if address is not None:\n        try:\n            if key:', '    if True:\n        try:\n            if key:', 'tests/test_window_provider.py::test_a_provider_that_takes_no_key_stores_none'),
    ('key: the error never holds the key', 'f"{address} (error {e.errno}). Nothing was changed.") from None', 'f"{address} (error {e.errno}). Nothing was changed. {key}") from None', 'tests/test_window_provider.py::test_when_credential_manager_fails_nothing_is_written_and_the_key_is_not_in_the_error'),
    ('key: the key is saved before the file', '        except OSError as e:\n            raise KeyNotSaved(', '        except KeyError as e:\n            raise KeyNotSaved(', 'tests/test_window_provider.py::test_when_credential_manager_fails_nothing_is_written_and_the_key_is_not_in_the_error'),
    ('key: the box hides what is typed', '        self.key_edit.setEchoMode(QLineEdit.Password)\n', '', 'tests/test_window_provider.py::test_the_key_box_hides_what_is_typed_and_never_shows_a_saved_key'),
    ('key: a saved key is never put in the box', '        self.key_edit.clear()\n        self.key_edit.setPlaceholderText("A key is saved.', '        self.key_edit.setText(\'x\')\n        self.key_edit.setPlaceholderText("A key is saved.', 'tests/test_window_provider.py::test_the_key_box_hides_what_is_typed_and_never_shows_a_saved_key'),
    ('provider: plain http with a key is refused', '            elif settings.key_sent_in_the_clear(self.url_edit.text().strip(), self.key_edit.text()):', '            elif False:', 'tests/test_window_provider.py::test_a_key_for_a_remote_http_address_is_not_saved'),
    ('provider: a server off this PC is announced', '    if not host or settings.this_pc(host):\n        return None\n', '    if not host:\n        return None\n', 'tests/test_window_provider.py::test_a_custom_provider_on_this_pc_does_not'),
    ('provider: only Custom sends text away', '    if provider != "custom":\n        return None\n    host', '    host', 'tests/test_window_provider.py::test_local_providers_never_warn'),
    ('halves: off frees the half', '            (half.start if on else half.stop)()\n', '            (half.start if on else half.start)()\n', 'tests/test_window_halves.py::test_turning_dictation_off_frees_only_dictation'),
    ('halves: both off is Paused', '        return "active" if self.dictation_on or self.reader_on else "paused"\n', '        return "active"\n', 'tests/test_window_halves.py::test_both_off_is_paused_and_says_so'),
    ('halves: no repeat of what is already so', '        if bool(half.running) == on:\n            return\n', '', 'tests/test_window_halves.py::test_switching_to_the_state_it_is_already_in_does_nothing'),
    ('halves: a failed start stays off and is not saved', '            self.problem.emit(f"{label} could not be turned', '            self._save(setting, on); self.problem.emit(f"{label} could not be turned', 'tests/test_window_halves.py::test_a_half_that_cannot_start_stays_off_and_reports_it'),
    ('hotkeys: Esc is refused', '    if parts == [CANCEL_KEY]:\n', '    if False:\n', 'tests/test_window_hotkeys.py::test_reserved_keys_are_refused'),
    ('hotkeys: Windows combinations are refused', '    if any(p in _WINDOWS_NAMES for p in parts):\n', '    if False:\n', 'tests/test_window_hotkeys.py::test_reserved_keys_are_refused'),
    ('hotkeys: a clash is reported', '        if name != own_name and _same_chord(key, other):\n', '        if False:\n', 'tests/test_window_hotkeys.py::test_a_clash_names_the_other_key_it_would_take'),
    ('hotkeys: a key does not clash with itself', '        if name != own_name and _same_chord(key, other):\n', '        if _same_chord(key, other):\n', 'tests/test_window_hotkeys.py::test_a_key_does_not_clash_with_itself'),
    ('hotkeys: F5 and F7 warn', '    if len(parts) == 1 and parts[0] in WARN_KEYS:\n', '    if False:\n', 'tests/test_window_hotkeys.py::test_browser_and_office_keys_warn_but_are_allowed'),
    ('hotkeys: a refused key is not taken', '        if self.verdict.level in ("ok", "warn"):\n', '        if True:\n', 'tests/test_window_hotkeys.py::test_esc_is_refused_not_taken'),
    ('window: only the two switches apply without a restart', '    return any(name not in LIVE for name in changed)\n', '    return bool(changed)\n', 'tests/test_window_settings.py::test_the_two_switches_do_not_restart_and_everything_else_does'),
    ('window: a missing microphone falls back', '    if not matches:\n        return None, True\n', '    if not matches:\n        return None, False\n', 'tests/test_window_settings.py::test_a_missing_microphone_falls_back_to_the_default_and_says_so'),
    ("restart: the new Engine waits for the old one's claim", '        if time.monotonic() >= deadline:\n', '        if True:\n', 'tests/test_processes.py::TestSecondCopyStopsAtTheDoor::test_a_restarted_engine_waits_for_the_old_one_to_let_go'),
    ('keys: the window lets go of the keys when it opens', '            self._keys_paused = True\n            self._keys_pause()\n', '            self._keys_paused = True\n', 'tests/test_window_settings.py::test_the_program_lets_go_of_its_keys_while_the_window_is_open'),
    ('keys: the window takes the keys back when it closes', '            self._keys_paused = False\n            self._keys_resume()\n', '            self._keys_paused = False\n', 'tests/test_window_settings.py::test_the_program_lets_go_of_its_keys_while_the_window_is_open'),
    ('keys: the engine binds them once when it resumes', '    if not _bound:\n        register_hotkeys()\n', '    if True:\n        register_hotkeys()\n', 'tests/test_window_settings.py::test_the_engine_lets_go_of_its_keys_and_takes_them_back_once'),
    ('keys: the engine really lets go', 'def pause_hotkeys() -> None:\n    """The Settings window is open: let go of the keys so a key pressed there reaches it."""\n    unregister_hotkeys()\n', 'def pause_hotkeys() -> None:\n    """The Settings window is open: let go of the keys so a key pressed there reaches it."""\n    return\n', 'tests/test_window_settings.py::test_the_engine_lets_go_of_its_keys_and_takes_them_back_once'),
    ('keys: the reader lets go too', '            unbind_keys() if paused else bind_keys()\n', '            bind_keys()\n', 'tests/test_window_settings.py::test_the_reader_follows_the_pause_and_binds_its_keys_again'),
    ('wizard: a settings file means no wizard', '    if os.path.exists(settings_path):\n        return False\n', '', 'tests/test_window_wizard.py::test_a_settings_file_means_no_wizard'),
    ('wizard: own old files mean the migration, not the wizard', '    return not old_files_are_mine(old_dir, owner, me)\n', '    return True\n', 'tests/test_window_wizard.py::test_any_old_file_to_migrate_means_no_wizard'),
    ("wizard: another user's old files are not migrated", '    return all(user is None or owner(path) in (None, user) for path in found)\n', '    return True\n', 'tests/test_window_wizard.py::test_another_users_old_files_mean_the_wizard_not_the_migration'),
    ("wizard: one file of another user is enough", '    return all(user is None or owner(path) in (None, user) for path in found)\n', '    return any(user is None or owner(path) in (None, user) for path in found)\n', 'tests/test_window_wizard.py::test_one_file_of_another_user_is_enough_to_not_migrate'),
    ('settings: nothing to migrate opens the wizard and writes no file', '_migrating = _first_start and first_run.old_files_are_mine(BASE_DIR)\n', '_migrating = _first_start\n', 'tests/test_window_wizard.py::test_a_first_start_with_nothing_to_migrate_writes_no_file_and_asks_for_setup'),
    ("settings: another user's .env is not migrated on a new account", '_migrating = _first_start and first_run.old_files_are_mine(BASE_DIR)\n', '_migrating = _first_start\n', 'tests/test_window_wizard.py::test_another_users_old_env_is_not_migrated_on_a_new_account'),
    ('settings: Run setup again asks for the wizard', '        self.setup_requested.emit()\n', '', 'tests/test_window_wizard.py::test_run_setup_again_in_settings_asks_for_the_wizard'),
    ('wizard: run again changes only what it asks', '            written.update({name: values[name] for name in ASKED})\n', '            written.update(values)\n', 'tests/test_window_wizard.py::test_run_again_keeps_the_settings_the_wizard_does_not_ask_about'),
    ('wizard: Arabic is right-to-left', '        self.setLayoutDirection(Qt.RightToLeft if i18n.is_rtl() else Qt.LeftToRight)\n        self.setWindowTitle(tr("wiz.title"))', '        self.setWindowTitle(tr("wiz.title"))', 'tests/test_window_wizard.py::test_arabic_switches_the_wizard_to_right_to_left_at_once'),
    ("wizard: the recommendation is recommend()'s", '    tier, preset, reasons = hardware.recommend(facts)\n', '    tier, preset, reasons = "cpu-only", {}, []\n', 'tests/test_window_wizard.py::test_the_recommendation_is_detect_then_recommend_unchanged'),
    ('wizard: the models folder is saved as MODELS_DIR', '            "MODELS_DIR": self.models_dir_edit.text().strip(),\n', '', 'tests/test_window_wizard.py::test_the_chosen_models_folder_is_saved_as_models_dir'),
    ('download: a cancelled one leaves nothing', '    except Cancelled:\n        _remove_new(cache_dir, before)\n', '    except Cancelled:\n', 'tests/test_window_wizard.py::test_a_cancelled_download_leaves_nothing_half_written'),
    ('download: a failed one leaves nothing', '    except Exception as e:\n        _remove_new(cache_dir, before)\n', '    except Exception as e:\n', 'tests/test_window_wizard.py::test_a_failed_download_leaves_nothing_half_written_and_says_why'),
    ('download: each report checks for Cancel', '        if cancel.is_set():\n            raise Cancelled()\n        done += count\n', '        done += count\n', 'tests/test_window_wizard.py::test_cancelling_the_real_download_stops_its_child_and_removes_its_files'),
    ('download: Cancel stops the child', '        if child.poll() is None:\n            child.kill()\n', '        if False:\n            child.kill()\n', 'tests/test_window_wizard.py::test_cancelling_the_real_download_stops_its_child_and_removes_its_files'),
    ('mic test: silence fails', '    if peak < MIC_MIN_PEAK:\n', '    if False:\n', 'tests/test_window_wizard.py::test_the_mic_test_fails_clearly'),
    ('AI test: no answer fails', '    if not answer or not str(answer).strip():\n', '    if False:\n', 'tests/test_window_wizard.py::test_the_ai_test_fails_clearly'),
    ('wizard key: it goes to Credential Manager', '            if address and key:\n                self.store.set(address, key)\n', '            if False:\n                self.store.set(address, key)\n', 'tests/test_window_wizard.py::test_the_api_key_goes_only_to_credential_manager'),
    ('wizard key: a refused key writes no settings file', '            self._say(tr("problem.key") + f"Windows Credential Manager (error {e.errno}).")\n            return False\n', '            self._say(tr("problem.key") + f"Windows Credential Manager (error {e.errno}).")\n', 'tests/test_window_wizard.py::test_a_key_that_cannot_be_stored_writes_no_settings_file'),
    ("wizard key: the AI test's file never holds it", '        storage.save(path, {n: v for n, v in values.items() if n != storage.KEY_NAME})\n', '        storage.save(path, {**{n: v for n, v in values.items() if n != storage.KEY_NAME}, "K": key})\n', 'tests/test_window_wizard.py::test_the_ai_tests_settings_file_never_holds_the_key'),
    ('wizard key: the AI test gets it on stdin', '            out, _ = child.communicate((key or "") + "\\n", timeout=AI_TEST_TIMEOUT)\n', '            out, _ = child.communicate("\\n", timeout=AI_TEST_TIMEOUT)\n', 'tests/test_window_wizard.py::test_the_ai_tests_settings_file_never_holds_the_key'),
    ('wizard keys: let go while it is open', '            self._keys_pause()\n            self._keys_paused = True\n', '            self._keys_paused = True\n', 'tests/test_window_wizard.py::test_the_program_lets_go_of_its_keys_while_the_wizard_is_open'),
    ('wizard keys: taken back when it closes', '            self._keys_resume()\n            self._keys_paused = False\n', '            self._keys_paused = False\n', 'tests/test_window_wizard.py::test_the_program_lets_go_of_its_keys_while_the_wizard_is_open'),
    ('keys: the pause is shared across processes', '    handle = _event(_KEYS_PAUSED_NAME, manual_reset=True)\n    if not handle:\n        return\n    if state:', '    handle = _event(_KEYS_PAUSED_NAME, manual_reset=True)\n    if not handle:\n        return\n    if False:', 'tests/test_window_settings.py::test_the_pause_is_shared_between_the_processes'),
    ('history: read newest first', '    return [entry for _, _, entry in reversed(_spans(_read(path)))]\n', '    return [entry for _, _, entry in _spans(_read(path))]\n', 'tests/test_window_history.py::test_entries_are_read_newest_first'),
    ('history: Delete one removes only that entry', '                _write(path, text[:start] + text[end:])\n', '                _write(path, text[:start])\n', 'tests/test_window_history.py::test_delete_one_removes_only_that_entry_and_is_saved'),
    ('history: Delete works on the file as it is now', '            history.delete_entry(entry, self.path)\n', "            history._write(self.path, ''.join(f'[{e.time}] [{e.mode}]\\n{e.text}\\n\\n' for e in reversed(self._entries) if e != entry))\n", 'tests/test_window_history.py::test_delete_keeps_a_dictation_written_while_the_viewer_was_open'),
    ('history: Clear all asks first', '        if self._entries and self._confirm(tr("hist.clear_ask")):\n', '        if self._entries:\n', 'tests/test_window_history.py::test_clear_all_declined_changes_nothing'),
    ('history: the viewer says when history is off', '        self.notice.setVisible(not keep_history)\n', '        self.notice.setVisible(False)\n', 'tests/test_window_history.py::test_with_history_off_the_viewer_says_so'),
    ('history: search filters', '        self._shown = [e for e in self._entries if wanted in e.text.casefold()]\n', '        self._shown = list(self._entries)\n', 'tests/test_window_history.py::test_search_finds_an_entry_ignoring_case'),
    ('history: Copy stays out of clipboard history', '    win_clipboard.set_text(text)\n', '    from PySide6.QtWidgets import QApplication; QApplication.clipboard().setText(text)\n', 'tests/test_window_history.py::test_copy_keeps_the_entry_out_of_clipboard_history'),
    ('vocabulary: edits hold the lock', '    with VOCAB_LOCK:\n        words = change(learned_words(path))\n', '    if True:\n        words = change(learned_words(path))\n', 'tests/test_window_vocabulary.py::test_writes_hold_the_vocabulary_lock'),
    ('vocabulary: an edit keeps a word learned meanwhile', '            vocabulary.change_learned_words(self.path, lambda words: [w for w in words if w != old])\n', '            vocabulary.change_learned_words(self.path, lambda words: [w for w in self.shown_words() if w != old])\n', 'tests/test_window_vocabulary.py::test_a_word_learned_while_the_editor_is_open_is_kept'),
    ('vocabulary: a repeated word is refused', '    if any(w.lower() == word.lower() for w in words if w != ignore):\n', '    if False:\n', 'tests/test_window_vocabulary.py::test_a_blank_or_repeated_word_is_refused'),
    ('vocabulary: Tidy runs on a worker', '        threading.Thread(target=self._run_tidy, daemon=True).start()\n', '        self._run_tidy()\n', 'tests/test_window_vocabulary.py::test_tidy_runs_on_a_worker_and_the_list_is_read_again'),
    ("vocabulary: Tidy is Shift+F1's maintenance", '    engine.run_memory_maintenance()\n', '    pass\n', 'tests/test_window_vocabulary.py::test_tidy_is_the_existing_maintenance'),
    ('data windows: let go of the keys when open', '            self._keys_let_go = True\n            self._on_open()\n', '            self._keys_let_go = True\n', 'tests/test_window_history.py::test_the_program_lets_go_of_its_keys_while_the_viewer_is_open'),
    ('data windows: take the keys back when closed', '            self._keys_let_go = False\n            self._on_close()\n', '            self._keys_let_go = False\n', 'tests/test_window_history.py::test_the_program_lets_go_of_its_keys_while_the_viewer_is_open'),
    ('diagnostics: a marked line is left out', '    if DICTATED_MARK in line:\n        return True\n', '', 'tests/test_diagnostics.py::test_marked_words_are_left_out_even_when_not_in_the_history'),
    ('diagnostics: a line with history text is left out', '    return any(piece in lowered for piece in private)\n', '    return False\n', 'tests/test_diagnostics.py::test_the_planted_dictated_words_are_never_in_it'),
    ('diagnostics: the saved key is hidden', '            text = text.replace(secret, HIDDEN)\n', '            pass\n', 'tests/test_diagnostics.py::test_the_saved_key_is_hidden_whatever_its_shape'),
    ('diagnostics: key shapes are hidden', '    for shape in KEY_SHAPES:\n', '    for shape in []:\n', 'tests/test_diagnostics.py::test_well_known_key_shapes_are_hidden_even_when_not_saved'),
    ('diagnostics: an address loses its user part', '    text = _USER_PART.sub(r"\\1", text)\n', '', 'tests/test_diagnostics.py::test_a_secret_in_an_address_is_hidden_but_the_server_is_shown'),
    ('diagnostics: an address loses its query', '    text = _QUERY.sub(r"\\1", text)\n', '', 'tests/test_diagnostics.py::test_a_secret_in_an_address_is_hidden_but_the_server_is_shown'),
    ('diagnostics: the key is not a setting', '    values.pop(storage.KEY_NAME, None)          # a key planted in the file is not shown\n', '', 'tests/test_diagnostics.py::test_the_settings_file_never_holds_a_key_even_when_planted'),
    ('diagnostics: 200 lines, into the backup', '    for name in (path, path + ".1", path + ".2"):\n', '    for name in (path,):\n', 'tests/test_diagnostics.py::test_it_holds_the_last_200_log_lines_reaching_into_the_backup'),
    ('log: dictated words carry the mark', '        return DICTATED_MARK + repr(text)\n', '        return repr(text)\n', 'tests/test_diagnostics.py::test_dictated_words_in_the_log_carry_a_mark_the_diagnostics_can_find'),
]

only = sys.argv[1] if len(sys.argv) > 1 else ""
failed = 0
for label, old, new, test in MUTATIONS:
    if only and only not in label:
        continue
    homes = [f for f in glob.glob("zeroflow/**/*.py", recursive=True) + glob.glob("reader/*.py")
             + ["zero_flow.py"]
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
        # Logs in a folder of this run's own, removed below: with the clean-up of the
        # tests' log folder broken on purpose, the tests would leave theirs in Temp.
        logs = tempfile.mkdtemp(prefix="zeroflow-mutation-")
        try:
            command = ([sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", test]
                       if "::" in test else [sys.executable, "-m", "unittest", test])
            run = subprocess.run(command, capture_output=True, text=True, timeout=120,
                                 env={**os.environ, "ZEROFLOW_LOG_DIR": logs})
        finally:
            shutil.rmtree(logs, ignore_errors=True)
        if "::" in test:                         # pytest: 1 is "a test failed"
            caught = run.returncode == 1
        else:
            caught = run.returncode != 0 and ("FAIL:" in run.stderr or "AssertionError" in run.stderr)
        print(f"{'CAUGHT ' if caught else 'MISSED '}  {label}")
        failed += not caught
    finally:
        shutil.move(path + ".mutbak", path)
print("all caught" if not failed else f"{failed} not caught")
sys.exit(1 if failed else 0)
