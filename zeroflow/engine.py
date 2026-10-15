"""
The dictation half: hotkey → record → transcribe → refine → paste.

Recording modes — each FORCES its language, so it can never misdetect:
    F5  English — raw          F6  English — polish
    F7  Arabic  — raw          F8  Arabic  — polish
    F9  Translate English → Arabic     F10  Translate Arabic → English
Action keys:
    Shift+F1  vocabulary maintenance   Shift+F2  clear log & history
    Shift+F3  fix the current line     Esc       cancel an in-progress recording

See ARCHITECTURE.md for the full design rationale.
"""
import logging
import os
import shutil
import sys
import threading
import time
import traceback

import keyboard
import numpy as np
import sounddevice as sd

# stt first: it loads faster-whisper, which must claim its CUDA libraries before any
# WinRT library (win11toast, via ui) is loaded. See zero_flow.py.
from zeroflow import stt
from zeroflow import personas, settings, signals, ui
from zeroflow.capture import Capture
from zeroflow.clipboard import copy_selection, paste_text, read_clipboard_context
from zeroflow.history import cap_history_file, log_to_history
from zeroflow.hotkeys import run_async, wait_for_release
from zeroflow.llm import ask_ai, model_name, warm_up_ai
from zeroflow.logs import init_logging
from zeroflow.paths import HISTORY_FILE, VOCAB_CACHE_FILE, log_path
from zeroflow.settings import (ENABLE_AUDIO_CHIMES, ENABLE_TOASTS, HOTKEYS,
                               MAX_RECORDING_SECONDS, WHISPER_MODEL_NAME)
from zeroflow.stt import SAMPLE_RATE, transcribe_audio
from zeroflow.text.language import ARABIC_LETTERS, checked_ai_output
from zeroflow.text.macros import apply_macros
from zeroflow.vocabulary import VOCAB_LOCK, load_vocabulary, vocabulary_terms

LOG_HANDLER = init_logging("flow")
LOG_FILE = log_path("flow")
logging.info("=== Zero- Core Application Boot Sequence Initiated ===")


# Each record hotkey maps to a recording mode. Forcing the language ("lang")
# removes language misdetection entirely. Operation ("op"):
#   raw       — inject the transcription as-is
#   polish    — LLM cleans grammar/fillers in the same language
#   translate — LLM translates to the target language ("to")
MODES = {
    "en_raw":    {"lang": "en", "op": "raw",       "label": "ENGLISH"},
    "en_polish": {"lang": "en", "op": "polish",    "label": "ENGLISH · POLISH"},
    "ar_raw":    {"lang": "ar", "op": "raw",       "label": "ARABIC"},
    "ar_polish": {"lang": "ar", "op": "polish",    "label": "ARABIC · POLISH"},
    "en2ar":     {"lang": "en", "op": "translate", "to": "ar", "label": "TRANSLATE EN→AR"},
    "ar2en":     {"lang": "ar", "op": "translate", "to": "en", "label": "TRANSLATE AR→EN"},
}


# Clips shorter than this (after capture) are dropped — they only ever produce
# Whisper hallucinations, never real words.
MIN_CLIP_SECONDS = 0.4


# The recording in progress (a Capture), or None. Each recording has its own audio and
# its own stop/cancel state: shared ones let quick presses mix up two recordings.
current_capture = None
capture_lock = threading.Lock()     # guards current_capture and the reader's mic signal


# One clip is transcribed → refined → pasted at a time. The next capture can start
# while the last is still being processed; this makes them land in the order they
# were spoken.
processing_lock = threading.Lock()


def run_memory_maintenance() -> None:
    """Shift+F1 — let the LLM dedupe / clean the learned-vocabulary file."""
    if is_recording():
        return
    print(f"\n{ui.C_WARN}🧹 AI Janitor: Analyzing and pruning vocabulary memory...{ui.C_RESET}")
    ui.show_toast("🧹 Memory Maintenance", "AI is optimizing your vocabulary files.", ENABLE_TOASTS)
    ui.update_console_title("MAINTENANCE RUNNING")

    before = sorted(load_vocabulary())
    current_vocab = "\n".join(before)
    answer = ask_ai(current_vocab, None, personas.MEMORY_MAINTENANCE_PROMPT)
    cleaned = "\n".join(vocabulary_terms(answer))
    if answer is None:
        print(f"{ui.C_WARN}⚠️  AI unavailable — the vocabulary is left as it was.{ui.C_RESET}")
    elif not cleaned or cleaned == current_vocab:
        print(f"{ui.C_WARN}🧹 Vocabulary unchanged — nothing written.{ui.C_RESET}")
    else:
        try:
            with VOCAB_LOCK:
                # A Polish may have learned a word while the LLM was working on the
                # old list; carry it over rather than overwrite it.
                added = [w for w in load_vocabulary() if w not in before]
                # The LLM rewrites a list you built up over time; keep the last version.
                if os.path.exists(VOCAB_CACHE_FILE):
                    shutil.copyfile(VOCAB_CACHE_FILE, VOCAB_CACHE_FILE + ".bak")
                with open(VOCAB_CACHE_FILE, "w", encoding="utf-8") as f:
                    f.write("\n".join([cleaned, *added]) + "\n")
            print(f"{ui.C_GOOD}✅ Vocabulary successfully compressed and organized "
                  f"(previous list saved as flow_vocabulary.txt.bak).{ui.C_RESET}")
            ui.show_toast("✅ Maintenance Complete", "Memory files pruned successfully.", ENABLE_TOASTS)
            ui.play_tone("clean", ENABLE_AUDIO_CHIMES)
        except Exception as e:
            logging.error(f"Vocabulary maintenance write failed: {e}")
            print(f"{ui.C_ERR}❌ Failed to write cleaned memory.{ui.C_RESET}")
    ui.update_console_title("ONLINE")


def purge_diagnostic_files() -> None:
    """Shift+F2 — clear the debug log and dictation history on demand. These are the
    files that grow with use; vocabulary is curated separately by Shift+F1.

    Clears this process's log only. The reader owns `reader_debug.log` and rotates it
    itself; truncating a file another process holds open would only corrupt it."""
    if is_recording():
        return
    try:
        open(HISTORY_FILE, "w", encoding="utf-8").close()
    except Exception as e:
        logging.error(f"History purge failed: {e}")
    # Released in `finally`: a handler lock left held would block every later log
    # call, freezing whichever thread logs next — which is most of them.
    LOG_HANDLER.acquire()
    try:
        LOG_HANDLER.stream.seek(0)
        LOG_HANDLER.stream.truncate()
    except Exception:
        pass
    finally:
        LOG_HANDLER.release()
    for suffix in (".1", ".2"):                  # also drop the rotated backups
        try:
            os.remove(LOG_FILE + suffix)
        except OSError:
            pass
    logging.info("Diagnostic files purged by user.")
    print(f"\n{ui.C_GOOD}🧹 Debug log & history cleared.{ui.C_RESET}")
    ui.show_toast("🧹 Cleaned", "Debug log and dictation history cleared.", ENABLE_TOASTS)
    ui.play_tone("clean", ENABLE_AUDIO_CHIMES)


def is_recording() -> bool:
    return current_capture is not None


def _end_capture(capture: Capture) -> None:
    """Forget `capture` if it is still the current one, and only then tell the reader
    the microphone is closed — a newer recording may already have it open again."""
    global current_capture
    with capture_lock:
        if current_capture is capture:
            current_capture = None
        if current_capture is None:
            signals.set_recording(False)
            ui.set_tray_state(False)


def _ai_unavailable(text: str) -> str:
    """The AI gave no answer (why is in the log and the toast): say so, and paste
    what was said rather than nothing."""
    print(f"{ui.C_WARN}⚠️  AI unavailable — pasted your own words: {ui.C_RESET}{text}")
    ui.play_tone("success_raw", ENABLE_AUDIO_CHIMES)
    return text


def refine_text(text: str, mode: str, context: str = "") -> str:
    """Apply the recording mode's operation. Raw modes pass straight through.
    `context` is the clipboard snapshot Polish mode hands the LLM."""
    cfg = MODES[mode]

    if cfg["op"] == "polish":
        ui.update_console_title("AI POLISHING")
        prompt = personas.ARABIC_POLISH_PROMPT if cfg["lang"] == "ar" else personas.STANDARD_SYSTEM_PROMPT
        answer = ask_ai(text, context, prompt)
        if answer is None:
            return _ai_unavailable(text)
        out = checked_ai_output(answer, text, cfg["lang"])
        print(f"✨ Polished: {ui.C_GOOD}{out}{ui.C_RESET}")
        ui.show_toast("✨ Polish Complete", "Cleaned prose injected.", ENABLE_TOASTS)
        ui.play_tone("success_polish", ENABLE_AUDIO_CHIMES)
        return out

    if cfg["op"] == "translate":
        ui.update_console_title("AI TRANSLATING")
        # Direction is fixed by the mode (not detected), so it's always correct.
        if cfg["to"] == "en":
            direction, prompt = "AR→EN", personas.TRANSLATE_TO_EN_PROMPT
        else:
            direction, prompt = "EN→AR", personas.TRANSLATE_TO_AR_PROMPT
        answer = ask_ai(text, None, prompt)
        if answer is None:
            return _ai_unavailable(text)
        out = checked_ai_output(answer, text, cfg["to"])
        print(f"🌐 Translated [{direction}]: {ui.C_WARN}{out}{ui.C_RESET}")
        ui.show_toast("🌐 Translation Complete", f"{direction} prose injected.", ENABLE_TOASTS)
        ui.play_tone("success_translate", ENABLE_AUDIO_CHIMES)
        return out

    ui.play_tone("success_raw", ENABLE_AUDIO_CHIMES)
    return text


def inject_text(text: str) -> None:
    """Apply spoken macros/punctuation, then paste the text at the cursor."""
    if not text:
        return
    text, lead_newline, end_enter = apply_macros(text)

    if lead_newline:
        keyboard.send('shift+enter')
        time.sleep(0.02)

    logging.info(f"Injecting text via clipboard paste: {text!r}")
    paste_text(text, press_enter=end_enter)


def process_recording(capture: Capture) -> None:
    """Open the mic, capture until stopped, then transcribe → refine → inject.

    Everything this recording needs travels in `capture`, because the next recording
    can start while this one is still closing its microphone or transcribing."""
    mode = capture.mode
    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                            callback=capture.callback, dtype='float32'):
            if not capture.stopped.wait(MAX_RECORDING_SECONDS):
                capture.stop()
                logging.info(f"Recording reached {MAX_RECORDING_SECONDS:.0f} s and stopped by itself.")
                print(f"\n{ui.C_WARN}⏱️  Recording stopped after {MAX_RECORDING_SECONDS:.0f} s "
                      f"(MAX_RECORDING_SECONDS).{ui.C_RESET}")
                ui.play_tone("stop", ENABLE_AUDIO_CHIMES)
    except Exception as e:
        capture.stop(cancel=True)
        logging.error(f"Audio InputStream failed to open: {e}")
        print(f"\n{ui.C_ERR}🎙️ Could not open the microphone: {e}{ui.C_RESET}")
        ui.play_tone("cancel", ENABLE_AUDIO_CHIMES)
        return
    finally:
        # The mic closes the moment the `with` block exits — release the reader here
        # rather than after transcription, so it only stays quiet while we listen.
        _end_capture(capture)
        if not is_recording():
            ui.update_console_title("ONLINE")

    sys.stdout.write("\r" + " " * 50 + "\r")     # wipe the live meter line

    if capture.cancelled:
        print(f"{ui.C_ERR}🛑 Audio flushed. Processing skipped.{ui.C_RESET}")
        return

    audio = capture.audio()
    if audio is None:
        ui.update_console_title("ONLINE")
        return
    if len(audio) / SAMPLE_RATE < MIN_CLIP_SECONDS:
        logging.info("Recording too short (<0.4s) — skipped to avoid hallucination on near-silence.")
        ui.play_tone("empty", ENABLE_AUDIO_CHIMES)
        ui.update_console_title("ONLINE")
        return

    # Read now, with the mic already closed: pyperclip can block for up to half a
    # second while another app holds the clipboard. On the keyboard hook that froze
    # the keyboard; before the mic opened it would cut off your first words.
    context = read_clipboard_context() if MODES[mode]["op"] == "polish" else ""

    with processing_lock:
        try:
            transcribe_and_inject(audio, mode, context)
        except Exception:
            # A clipboard held by another app, say. Without this the thread would die
            # silently, leaving the title stuck on DECODING and nothing in the log.
            logging.error(f"Processing the recording failed: {traceback.format_exc()}")
            print(f"{ui.C_ERR}❌ Processing failed — details in flow_debug.log.{ui.C_RESET}")
            ui.play_tone("empty", ENABLE_AUDIO_CHIMES)
        finally:
            ui.update_console_title("ONLINE")


def transcribe_and_inject(audio: np.ndarray, mode: str, context: str) -> None:
    """Stages 2-4 for one captured clip: transcribe, refine, paste."""
    ui.update_console_title("DECODING")
    started = time.time()
    text, lang = transcribe_audio(audio, MODES[mode]["lang"])
    # The speed figure docs/HARDWARE.md tunes against: seconds spent per clip.
    took = time.time() - started
    logging.info(f"Transcription result (mode={mode}, lang={lang}, "
                 f"{took:.2f}s for {len(audio) / SAMPLE_RATE:.1f}s of audio): {text!r}")

    if text is None:
        logging.info("Transcription failed — nothing injected (the error is logged above).")
        print(f"{ui.C_ERR}❌ Transcription failed — details in flow_debug.log.{ui.C_RESET}")
        ui.play_tone("empty", ENABLE_AUDIO_CHIMES)
        return
    if not text:
        logging.info("Empty transcription — nothing injected (silence / VAD dropped all audio).")
        ui.play_tone("empty", ENABLE_AUDIO_CHIMES)
        return

    print(f"📝 Raw ({took:.1f}s): {text}")
    text = refine_text(text, mode, context)
    inject_text(text)
    log_to_history(text, mode)


def on_record_hotkey(mode_name: str) -> None:
    """A record key (F5–F10) was pressed: start a capture in that mode, or stop it."""
    global current_capture

    with capture_lock:
        capture = current_capture
        if capture is None:
            capture = current_capture = Capture(mode_name)
            # Tell the reader to stop talking and stay quiet: a live mic would otherwise
            # pick up the synthetic voice and Whisper would transcribe the engine
            # reading to itself.
            signals.request_reader_silence()
            signals.set_recording(True)
            ui.set_tray_state(True)
            starting = True
        else:
            # Any record key stops the capture. The mode is locked in at the start —
            # we never switch modes mid-recording (that caused surprise translations).
            current_capture = None
            starting = False
    if starting:
        print(f"\n{ui.C_ACCENT}🔴 [{MODES[mode_name]['label']}] Capturing audio...{ui.C_RESET}")
        ui.play_tone("start", ENABLE_AUDIO_CHIMES)
        threading.Thread(target=process_recording, args=(capture,)).start()
    else:
        capture.stop()
        ui.set_tray_state(False)
        ui.play_tone("stop", ENABLE_AUDIO_CHIMES)


def on_cancel_hotkey() -> None:
    """Esc — cancel an in-progress recording. (Does nothing when idle, so Esc keeps
    working normally in your apps; use the app's own Ctrl+Z to undo an injection.)"""
    global current_capture
    with capture_lock:
        capture, current_capture = current_capture, None
    if capture is not None:
        capture.stop(cancel=True)
        ui.set_tray_state(False)
        print(f"\n{ui.C_ERR}🛑 Recording cancelled.{ui.C_RESET}")
        ui.play_tone("cancel", ENABLE_AUDIO_CHIMES)


def correct_current_line() -> None:
    """Shift+F3 — grab the current line, fix it via the LLM, paste it back."""
    if is_recording():
        return
    print(f"\n{ui.C_ACCENT}⚡ Running contextual line refinement...{ui.C_RESET}")
    ui.play_tone("start", ENABLE_AUDIO_CHIMES)
    # Still holding Shift from Shift+F3 would turn the Ctrl+C below into Ctrl+Shift+C
    # (DevTools in a browser) — wait for the keys to come up first.
    wait_for_release(HOTKEYS["fix"])

    # Select back to the start of the line and copy it (the clipboard lock is held for
    # the copy, not across the LLM call below, which can take seconds).
    target_text = copy_selection(select="shift+home")
    if not target_text:
        ui.play_tone("empty", ENABLE_AUDIO_CHIMES)
        return

    lang = "ar" if ARABIC_LETTERS.search(target_text) else "en"
    fixed = ask_ai(target_text, None, personas.LINE_CORRECTION_PROMPT)
    if fixed is None:
        print(f"{ui.C_WARN}⚠️  AI unavailable — the line is left as it was.{ui.C_RESET}")
    else:
        fixed = checked_ai_output(fixed, target_text, lang)
    if fixed and fixed != target_text:
        print(f"✨ Optimized: '{ui.C_GOOD}{fixed}{ui.C_RESET}'")
        paste_text(fixed)                        # replaces the still-selected line
        ui.play_tone("correction", ENABLE_AUDIO_CHIMES)
        log_to_history(fixed, "line_fix")
    else:
        keyboard.send('right')                   # deselect, leave the line untouched
        ui.play_tone("stop", ENABLE_AUDIO_CHIMES)


def boot() -> None:
    """Load the model and get the dictation half ready. Shared by both entry points
    (this file standalone, and the supervisor in zero_flow.py)."""

    ui.update_console_title("INITIALIZING HARDWARE")
    ui.report_setting_problems(settings.problems, ENABLE_TOASTS)
    # Clear any stale recording flag left behind if a previous run was force-killed
    # mid-capture — otherwise a running reader would keep refusing to speak.
    signals.set_recording(False)
    # Load the AI model alongside Whisper rather than on the first Polish (3-12 s).
    threading.Thread(target=warm_up_ai, daemon=True).start()
    stt.model = stt.load_whisper_model()
    cap_history_file()
    ui.update_console_title("ONLINE")


def register_hotkeys() -> None:
    """Bind the dictation keys. Shared by both entry points."""
    # Record modes (F5–F10). suppress=True consumes the key so it never reaches the
    # focused app (e.g. F5 = browser refresh). The lambda captures each mode name.
    for mode in MODES:
        keyboard.add_hotkey(HOTKEYS[mode], (lambda m: lambda: on_record_hotkey(m))(mode), suppress=True)

    # Action keys do heavy work (LLM calls, key-sending), so dispatch each to a worker
    # thread — never block the keyboard listener (that froze the whole keyboard).
    keyboard.add_hotkey(HOTKEYS["fix"],         run_async(correct_current_line), suppress=True)
    keyboard.add_hotkey(HOTKEYS["maintenance"], run_async(run_memory_maintenance), suppress=True)
    keyboard.add_hotkey(HOTKEYS["purge"],       run_async(purge_diagnostic_files), suppress=True)
    keyboard.add_hotkey(HOTKEYS["panic"],       on_cancel_hotkey)


def report_fatal_error(what: str) -> None:
    """The engine cannot run. Log why, and say so where the user will see it —
    started hidden, a console message alone is never seen."""
    logging.critical(f"Fatal {what} crash: {traceback.format_exc()}")
    print(f"{ui.C_ERR}❌ The {what} stopped with an error — details in flow_debug.log.{ui.C_RESET}")
    ui.alert("Zero- Flow stopped", f"The {what} stopped with an error and is not running.\n\n"
                                   f"The details are in flow_debug.log, in the program folder.")


def run() -> int:
    """Run the dictation half on its own (local_flow.py); exit code 1 after a crash."""
    try:
        main()
    except Exception:
        report_fatal_error("dictation engine")
        return 1
    return 0


def key_sections(panic: str = "cancel") -> list:
    """The dictation keys, for the start-up banner — as set in .env, not as shipped."""
    hk, magenta = HOTKEYS, ui.Fore.MAGENTA
    return [
        ("DICTATE", "the key forces the language", [
            [(hk["en_raw"], "English · raw   ", ui.C_ACCENT), (hk["en_polish"], "English · polish", ui.C_GOOD)],
            [(hk["ar_raw"], "Arabic · raw    ", ui.C_WARN), (hk["ar_polish"], "Arabic · polish", ui.C_WARN)]]),
        ("TRANSLATE", None, [
            [(hk["en2ar"], "English → Arabic", magenta), (hk["ar2en"], "Arabic → English", magenta)]]),
        ("ACTIONS", None, [
            [(hk["fix"], "fix line", ui.C_GOOD), (hk["maintenance"], "vocab cleanup", magenta),
             (hk["purge"], "clear logs", ui.C_GOOD), (hk["panic"], panic, ui.C_ERR)]]),
    ]


def show_banner() -> None:
    """The banner of the dictation half on its own."""
    ui.print_banner("Z E R O -   F L O W   E N G I N E",
                    [("Speech to text", f"Whisper {WHISPER_MODEL_NAME} · {stt.model_runtime}"),
                     ("AI model", model_name())],
                    key_sections())


def main() -> None:
    if not signals.claim_single_instance("dictation"):
        ui.already_running()
        return
    boot()
    show_banner()
    ui.show_toast("🚀 Zero- Flow Online", "Background engine is active and listening.", ENABLE_TOASTS)
    ui.setup_system_tray()
    ui.set_window_icon()
    register_hotkeys()
    keyboard.wait()
