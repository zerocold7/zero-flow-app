"""
Zero- Flow Engine — local, bilingual (Arabic / English) voice dictation for Windows 11.

Pipeline:  hotkey  →  record mic  →  faster-whisper transcribe  →  (optional Ollama
refine)  →  paste into the focused app.

Recording modes — each FORCES its language, so it can never misdetect:
    F5  English — raw          F6  English — polish
    F7  Arabic  — raw          F8  Arabic  — polish
    F9  Translate English → Arabic     F10  Translate Arabic → English
Action keys:
    Shift+F1  vocabulary maintenance   Shift+F2  clear log & history
    Shift+F3  fix the current line     Esc       cancel an in-progress recording

The text-to-speech half of the engine lives in `reader/` (F4 reads the highlighted
selection aloud). Both halves share `flow_core.py`, `personas.py` and `engine_ui.py`.

See ARCHITECTURE.md for the full design rationale.
"""
import os
import sys
import time
import shutil
import threading
import re
import logging
import traceback
from datetime import datetime

import numpy as np
import sounddevice as sd
import soundfile as sf
import keyboard
import pyperclip

# CTranslate2 (faster-whisper's engine) imports torch and transformers on import, for
# its model *converters* — about 6 s, on every start, for code this engine never runs.
# The import is optional (try/except ImportError) and only succeeds because the
# reader's voice needs both installed. Marking them unavailable for this one import
# makes the engine ready ~5 s sooner and keeps torch out of the dictation process.
# Guarded by tests/test_startup.py.
_skipped = [name for name in ("torch", "transformers") if name not in sys.modules]
sys.modules.update(dict.fromkeys(_skipped))      # None: "import X" raises ImportError
try:
    from faster_whisper import WhisperModel
    from faster_whisper.utils import download_model
finally:
    for _name in _skipped:
        sys.modules.pop(_name, None)                 # a later real import still works
from huggingface_hub.utils import logging as hf_logging

try:
    import personas
    import engine_ui as ui
    import flow_signals as signals
    from flow_core import (
        clipboard_lock, VOCAB_CACHE_FILE, VOCAB_LOCK, TEMP_AUDIO_FILE, HISTORY_FILE,
        ENABLE_AUDIO_CHIMES, ENABLE_TOASTS, FOREIGN_SCRIPT,
        init_logging, log_path, get_ollama_model, load_vocabulary, query_ollama,
        ask_ollama, warm_up_llm,
    )
except ImportError as e:
    print(f"❌ Critical error: Missing local module: {e}")
    sys.exit(1)

LOG_HANDLER = init_logging("flow")
LOG_FILE = log_path("flow")
logging.info("=== Zero- Core Application Boot Sequence Initiated ===")
# A first-run model download is an anonymous Hub request, which the Hub answers with a
# "set a HF_TOKEN" notice about rate limits. The models are public and fetched once;
# the notice is noise. (Every later boot reads the cache and asks the Hub nothing.)
hf_logging.set_verbosity_error()

# =====================================================================
# CONFIGURATION
# =====================================================================
# Dictation-only settings live here; everything shared with the reader (paths, the
# debug log, the LLM client, vocabulary, chimes/toasts) comes from flow_core.
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL_NAME", "large-v3")
# "auto" tries the NVIDIA GPU and falls back to the CPU; "cpu" skips the GPU attempt
# (no NVIDIA card, or to leave the card's memory to the local LLM).
WHISPER_DEVICE     = os.getenv("WHISPER_DEVICE", "auto").strip().lower()
# GPU precision. "int8_float16" halves the speech model's graphics memory — large-v3
# measured 3.9 GB -> 2.0 GB on an RTX 4070, 0.9 s -> 1.1 s per 14 s clip. The CPU
# fallback always uses int8, the only precision that is fast there.
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "float16").strip().lower()
SAMPLE_RATE        = int(os.getenv("SAMPLE_RATE", 16000))
CHANNELS           = int(os.getenv("CHANNELS", 1))

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

HOTKEYS = {
    "en_raw":      os.getenv("HOTKEY_EN_RAW", "f5"),
    "en_polish":   os.getenv("HOTKEY_EN_POLISH", "f6"),
    "ar_raw":      os.getenv("HOTKEY_AR_RAW", "f7"),
    "ar_polish":   os.getenv("HOTKEY_AR_POLISH", "f8"),
    "en2ar":       os.getenv("HOTKEY_EN2AR", "f9"),
    "ar2en":       os.getenv("HOTKEY_AR2EN", "f10"),
    "fix":         os.getenv("HOTKEY_FIX", "shift+f3"),
    "maintenance": os.getenv("HOTKEY_MAINTENANCE", "shift+f1"),
    "purge":       os.getenv("HOTKEY_PURGE", "shift+f2"),
    "panic":       os.getenv("HOTKEY_PANIC", "esc"),
}

# This engine only ever speaks Arabic or English; anything else is a misdetection.
SUPPORTED_LANGS = ("ar", "en")
# Clips shorter than this (after capture) are dropped — they only ever produce
# Whisper hallucinations, never real words.
MIN_CLIP_SECONDS = 0.4
# A recording left running stops by itself after this long, and is transcribed as
# usual. Without a limit a forgotten one grew by ~4 MB a minute.
MAX_RECORDING_SECONDS = float(os.getenv("MAX_RECORDING_SECONDS", 300))
# flow_history.md is trimmed back to its newest content once it grows past this.
HISTORY_MAX_BYTES = 500_000

URL_PATTERN = re.compile(r'https?://\S+|www\.\S+')

ARABIC_LETTERS = re.compile(r'[\u0621-\u064A]')
LATIN_LETTERS = re.compile(r'[A-Za-z]')
# Arabic vowel marks and shadda, stripped from the AI's Arabic: models add them unasked
# ("لنُحدِّث"), and prose is written without. Tanween fath (U+064B) is kept — "جدًا" and
# "شكرًا" spell it as standard.
ARABIC_MARKS = re.compile(r'[\u064C-\u0652\u0670]')

# Whisper punctuates what it hears, so a spoken macro rarely arrives bare: "New line.
# Hello." / "See you then, and send." Macros are matched through this punctuation.
MACRO_PUNCT = r'[\s,.;:!?،؛؟…]'
TRAILING_PUNCT = re.compile(MACRO_PUNCT + r'+$')
# LLMs like to answer "list the words" with "- word" or "1. word"; keep only the word.
LIST_MARKER = re.compile(r'^\s*(?:[-*•]|\d+[.)])\s+')
# A vocabulary term is a name or phrase ("Visual Studio Code"), never a sentence.
MAX_TERM_WORDS = 4

# =====================================================================
# RUNTIME STATE (set in main / mutated by the hotkey + worker threads)
# =====================================================================
model = None              # faster-whisper model, loaded in main()
model_runtime = ""        # where it runs, e.g. "GPU · float16" — shown in the banner
# The recording in progress (a Capture), or None. Each recording has its own audio and
# its own stop/cancel state: shared ones let quick presses mix up two recordings.
current_capture = None
capture_lock = threading.Lock()     # guards current_capture and the reader's mic signal
# One clip is transcribed → refined → pasted at a time. The next capture can start
# while the last is still being processed; this keeps them from sharing the temp WAV
# and makes them land in the order they were spoken.
processing_lock = threading.Lock()

# =====================================================================
# HARDWARE / SERVICE DISCOVERY
# =====================================================================
def resolve_whisper_model():
    """The Whisper model's folder on disk: straight from the local cache when it is
    there, downloaded only when it is not (the first run, or a new WHISPER_MODEL_NAME).

    Handing WhisperModel the bare name instead makes it ask the Hugging Face Hub for
    the latest revision on every boot, cached or not — a network call a local engine
    has no need for, and a stall at start-up whenever there is no internet."""
    if os.path.isdir(WHISPER_MODEL_NAME):
        return WHISPER_MODEL_NAME                # a local model folder was configured
    try:
        return download_model(WHISPER_MODEL_NAME, local_files_only=True)
    except FileNotFoundError:                    # huggingface_hub's LocalEntryNotFoundError
        logging.info(f"Whisper model '{WHISPER_MODEL_NAME}' is not cached yet; downloading it.")
        print(f"{ui.C_ACCENT}⬇️  Downloading the speech model '{WHISPER_MODEL_NAME}' "
              f"(first run only)...{ui.C_RESET}")
        return download_model(WHISPER_MODEL_NAME)


def load_whisper_model():
    """Load faster-whisper on the GPU (unless WHISPER_DEVICE=cpu), verifying with a real
    inference so a missing CUDA library falls back to CPU at boot instead of crashing
    mid-dictation. Records where it ended up in `model_runtime`."""
    global model_runtime
    model_path = resolve_whisper_model()
    if WHISPER_DEVICE != "cpu":
        # Make any pip-installed CUDA DLLs (nvidia-cublas-cu12 / nvidia-cudnn-cu12) findable.
        for entry in sys.path:
            for lib in ("cublas", "cudnn"):
                bin_dir = os.path.join(entry, "nvidia", lib, "bin")
                if os.path.isdir(bin_dir):
                    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                    if hasattr(os, "add_dll_directory"):
                        os.add_dll_directory(bin_dir)
        try:
            m = WhisperModel(model_path, device="cuda", compute_type=WHISPER_COMPUTE_TYPE)
            # CTranslate2 loads the CUDA libs lazily on first inference, so force a tiny
            # real decode now — any GPU failure surfaces here and falls back cleanly.
            list(m.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), vad_filter=False)[0])
            model_runtime = f"GPU · {WHISPER_COMPUTE_TYPE}"
            logging.info(f"Whisper model active on CUDA ({WHISPER_COMPUTE_TYPE}).")
            return m
        except Exception as e:
            logging.warning(f"CUDA unavailable ({e}); falling back to CPU (int8).")
    m = WhisperModel(model_path, device="cpu", compute_type="int8")
    model_runtime = "CPU · int8"
    logging.info("Whisper model active on CPU (int8).")
    return m

# =====================================================================
# HISTORY
# =====================================================================
def log_to_history(text, mode):
    if not text:
        return
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] [{mode.upper()}]\n{text}\n\n")
    except Exception as e:
        logging.error(f"History write fail: {e}")
    cap_history_file()

# Where each history entry starts: its "[12:34:56] [MODE]" header at a line start.
HISTORY_ENTRY = re.compile(r"^\[\d\d:\d\d:\d\d\] \[", re.MULTILINE)

def cap_history_file():
    """Trim flow_history.md to about half of HISTORY_MAX_BYTES once it passes the cap,
    so the dictation history can never grow without bound. Runs after every write.

    The cut lands on an entry's first line, so no dictation is kept half-written."""
    try:
        if not os.path.exists(HISTORY_FILE) or os.path.getsize(HISTORY_FILE) <= HISTORY_MAX_BYTES:
            return
        with open(HISTORY_FILE, encoding="utf-8") as f:
            text = f.read()
        tail = text.encode("utf-8")[-(HISTORY_MAX_BYTES // 2):].decode("utf-8", "ignore")
        start = HISTORY_ENTRY.search(tail)
        kept = tail[start.start():] if start else ""
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            f.write(f"[... older history trimmed on {datetime.now():%Y-%m-%d %H:%M} ...]\n\n{kept}")
        logging.info("flow_history.md trimmed (exceeded size cap).")
    except Exception as e:
        logging.error(f"History cap failed: {e}")

def vocabulary_terms(llm_output):
    """The terms in the LLM's answer to "clean up this list", without its chatter.

    Models wrap the list in sentences ("Here is the cleaned list:", "I removed the
    duplicates..."). Kept, each became a "word" and was fed to Whisper as a hint on
    every dictation. A term is short and never introduces something with a colon."""
    terms = []
    for line in (llm_output or "").splitlines():
        term = LIST_MARKER.sub('', line).strip()
        if term and not term.endswith(":") and len(term.split()) <= MAX_TERM_WORDS:
            terms.append(term)
    return terms


def run_memory_maintenance():
    """Shift+F1 — let the LLM dedupe / clean the learned-vocabulary file."""
    if is_recording():
        return
    print(f"\n{ui.C_WARN}🧹 AI Janitor: Analyzing and pruning vocabulary memory...{ui.C_RESET}")
    ui.show_toast("🧹 Memory Maintenance", "AI is optimizing your vocabulary files.", ENABLE_TOASTS)
    ui.update_console_title("MAINTENANCE RUNNING")

    before = sorted(load_vocabulary())
    current_vocab = "\n".join(before)
    cleaned = "\n".join(vocabulary_terms(
        query_ollama(current_vocab, None, personas.MEMORY_MAINTENANCE_PROMPT)))
    if not cleaned or cleaned == current_vocab:
        # query_ollama hands back its input when the LLM is unreachable, so an
        # unchanged list is not a success worth rewriting the file for.
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

def purge_diagnostic_files():
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

# =====================================================================
# AUDIO CAPTURE & TRANSCRIPTION
# =====================================================================
class Capture:
    """One recording: its mode, its audio, and whether it was stopped or cancelled.

    Nothing here is shared with the next recording, which can start the moment this
    one is stopped — while this one's microphone is still closing."""

    def __init__(self, mode):
        self.mode = mode
        self._chunks = []
        self.stopped = threading.Event()
        self.cancelled = False

    def callback(self, indata, frames, time_info, status):
        """sounddevice callback: keep the audio and draw a live level meter."""
        if self.stopped.is_set():
            return
        self._chunks.append(indata.copy())
        level = int(min(np.linalg.norm(indata) * 10, 20))
        bars = "|" * level + " " * (20 - level)
        sys.stdout.write(f"\r{ui.C_ACCENT}[{ui.C_GOOD}{bars}{ui.C_ACCENT}] Capturing Voice Data...{ui.C_RESET}")
        sys.stdout.flush()

    def stop(self, cancel=False):
        self.cancelled = self.cancelled or cancel
        self.stopped.set()

    def audio(self):
        """Everything captured, as one array, or None if nothing was."""
        return np.concatenate(self._chunks, axis=0) if self._chunks else None


def is_recording():
    return current_capture is not None


def _end_capture(capture):
    """Forget `capture` if it is still the current one, and only then tell the reader
    the microphone is closed — a newer recording may already have it open again."""
    global current_capture
    with capture_lock:
        if current_capture is capture:
            current_capture = None
        if current_capture is None:
            signals.set_recording(False)
            ui.set_tray_state(False)

def whisper_hint(language):
    """Whisper's hint (initial_prompt) for one language: text in that language only.

    Whisper reads the hint as the text that came just before, so its language and style
    carry over. Priming Arabic with the shared vocabulary — mostly Latin-script tech
    terms — raised character errors from ~38% to ~49% on the Arabic test clips and left
    the output unpunctuated. Arabic gets a short punctuated Arabic sentence plus any
    Arabic terms; English gets the Latin-script terms. Sorted, so the hint is the same
    from one run to the next.
    """
    vocab = sorted(load_vocabulary())
    arabic_terms = [w for w in vocab if ARABIC_LETTERS.search(w)]
    if language == "ar":
        return " ".join([personas.ARABIC_WHISPER_HINT] + (["، ".join(arabic_terms)] if arabic_terms else []))
    if language == "en":
        vocab = [w for w in vocab if not ARABIC_LETTERS.search(w)]
    return ", ".join(vocab) or None


def transcribe_clip(force_lang):
    """Decode TEMP_AUDIO_FILE → (text, language).

    force_lang ('en' or 'ar') forces the output language — no detection, so it can
    never mishear English as Arabic. If force_lang is None it auto-detects, and if
    Whisper drifts to a third language (gibberish) it re-decodes as the closer one.

    Returns (None, None) when transcription failed — distinct from ("", lang), which
    means it ran and heard no speech. A failure on the graphics card (typically out of
    memory: Whisper, the voice and the AI model share it) retries the clip on the CPU.
    """
    def decode(whisper, language):
        # condition_on_previous_text=False prevents repetition-loop hallucinations;
        # beam_size=5 gives steadier decoding on short clips.
        segments, info = whisper.transcribe(
            TEMP_AUDIO_FILE, beam_size=5, vad_filter=True,
            condition_on_previous_text=False, language=language,
            initial_prompt=whisper_hint(language),
        )
        return "".join(s.text for s in segments).strip(), info

    def run(whisper):
        text, info = decode(whisper, force_lang)
        lang = force_lang or info.language
        if force_lang is None and lang not in SUPPORTED_LANGS:
            probs = dict(getattr(info, "all_language_probs", None) or [])
            lang = "ar" if probs.get("ar", 0) >= probs.get("en", 0) else "en"
            logging.warning(f"Detected non-ar/en language — re-decoding as '{lang}'.")
            text, _ = decode(whisper, lang)
        return text, lang

    try:
        return run(model)
    except Exception as e:
        if not model_runtime.startswith("GPU"):
            logging.error(f"Whisper transcription failed: {e}")
            return None, None
        logging.warning(f"Whisper failed on the graphics card ({e}); transcribing this clip on the CPU.")
    try:
        return run(cpu_fallback_model())
    except Exception as e:
        logging.error(f"Whisper transcription failed on the CPU too: {e}")
        return None, None


_cpu_model = None        # loaded on the first GPU failure, then kept for later ones

def cpu_fallback_model():
    """A CPU copy of the speech model, for clips the graphics card could not take."""
    global _cpu_model
    if _cpu_model is None:
        _cpu_model = WhisperModel(resolve_whisper_model(), device="cpu", compute_type="int8")
        logging.info("Loaded a CPU copy of the speech model for graphics-card failures.")
    return _cpu_model

# =====================================================================
# TEXT REFINEMENT & INJECTION
# =====================================================================
def checked_ai_output(output, original, lang):
    """The AI's text if it is in the language asked for — otherwise the original words.

    Better to paste what you said, unpolished, than to paste Chinese: qwen2.5:7b
    answered Arabic Polish in Chinese in 5 tries out of 5. Arabic output also loses the
    vowel marks models add unasked."""
    if output == original:                       # the AI was unreachable: nothing to check
        return output
    wanted = ARABIC_LETTERS if lang == "ar" else LATIN_LETTERS
    if FOREIGN_SCRIPT.search(output) or not wanted.search(output):
        logging.warning(f"The AI did not answer in '{lang}'; pasting the original instead: "
                        f"{output[:120]!r}")
        print(f"{ui.C_WARN}⚠️  The AI answered in the wrong language — pasting your own words.{ui.C_RESET}")
        return original
    return ARABIC_MARKS.sub("", output) if lang == "ar" else output


def _ai_unavailable(text):
    """The AI gave no answer (why is in the log and the toast): say so, and paste
    what was said rather than nothing."""
    print(f"{ui.C_WARN}⚠️  AI unavailable — pasted your own words: {ui.C_RESET}{text}")
    ui.play_tone("success_raw", ENABLE_AUDIO_CHIMES)
    return text


def refine_text(text, mode, context=""):
    """Apply the recording mode's operation. Raw modes pass straight through.
    `context` is the clipboard snapshot Polish mode hands the LLM."""
    cfg = MODES[mode]

    if cfg["op"] == "polish":
        ui.update_console_title("OLLAMA PROCESSING")
        prompt = personas.ARABIC_POLISH_PROMPT if cfg["lang"] == "ar" else personas.STANDARD_SYSTEM_PROMPT
        answer = ask_ollama(text, context, prompt)
        if answer is None:
            return _ai_unavailable(text)
        out = checked_ai_output(answer, text, cfg["lang"])
        print(f"✨ Polished: {ui.C_GOOD}{out}{ui.C_RESET}")
        ui.show_toast("✨ Polish Complete", "Cleaned prose injected.", ENABLE_TOASTS)
        ui.play_tone("success_polish", ENABLE_AUDIO_CHIMES)
        return out

    if cfg["op"] == "translate":
        ui.update_console_title("OLLAMA TRANSLATING")
        # Direction is fixed by the mode (not detected), so it's always correct.
        if cfg["to"] == "en":
            direction, prompt = "AR→EN", personas.TRANSLATE_TO_EN_PROMPT
        else:
            direction, prompt = "EN→AR", personas.TRANSLATE_TO_AR_PROMPT
        answer = ask_ollama(text, None, prompt)
        if answer is None:
            return _ai_unavailable(text)
        out = checked_ai_output(answer, text, cfg["to"])
        print(f"🌐 Translated [{direction}]: {ui.C_WARN}{out}{ui.C_RESET}")
        ui.show_toast("🌐 Translation Complete", f"{direction} prose injected.", ENABLE_TOASTS)
        ui.play_tone("success_translate", ENABLE_AUDIO_CHIMES)
        return out

    ui.play_tone("success_raw", ENABLE_AUDIO_CHIMES)
    return text

def _phrases(tokens):
    """Trigger phrases as one regex alternation, longest first."""
    return "|".join(re.escape(t) for t in sorted(tokens, key=len, reverse=True))


def _strip_leading(text, tokens):
    """Remove a leading trigger phrase and the punctuation Whisper put after it.
    Whole words only: "Pointless" is not the "point" macro. Returns (text, matched)."""
    pattern = r'(?i)^(?:%s)(?!\w)%s*' % (_phrases(tokens), MACRO_PUNCT)
    stripped = re.sub(pattern, '', text, count=1)
    return stripped, stripped != text


def _strip_trailing(text, tokens):
    """Remove a trailing trigger phrase, the comma Whisper puts before it and the mark
    after it — but not the speaker's own "!" or "?" in front. Whole words only: "a
    thousand send" is not the "and send" macro. Returns (text, matched)."""
    pattern = r'(?i)[\s,،]*(?<!\w)(?:%s)%s*$' % (_phrases(tokens), MACRO_PUNCT)
    stripped = re.sub(pattern, '', text, count=1)
    return stripped, stripped != text


def apply_macros(text):
    """Turn a raw transcription into the exact string to paste.

    Spoken macros ("new line", "bullet", "format code", "and send") are detected,
    stripped, and turned into formatting; spoken punctuation becomes real punctuation;
    known vocabulary is re-cased. Returns `(text, lead_newline, end_enter)` — the two
    flags being keystrokes the caller has to send, since they cannot live in a string.

    Kept separate from `inject_text` so this logic is testable without driving the
    keyboard and clipboard. See tests/test_macros.py.
    """
    macros = personas.VOICE_MACROS
    text = text.strip()

    # At most one leading macro; press_enter is the trailing one.
    lead = None
    for name in ("new_line", "bullet", "code_block"):
        text, matched = _strip_leading(text, macros[name])
        if matched:
            lead = name
            break
    lead_newline = lead == "new_line"
    lead_bullet = lead == "bullet"
    wrap_code = lead == "code_block"
    text, end_enter = _strip_trailing(text, macros["press_enter"])

    # Spoken punctuation is matched without Whisper's own closing mark, which would
    # otherwise hide it: "That is all, period." → "That is all."
    bare = TRAILING_PUNCT.sub('', text)
    if any(re.search(pattern, bare) for pattern in personas.PUNCTUATION_MAP):
        text = bare
        for pattern, replacement in personas.PUNCTUATION_MAP.items():
            text = re.sub(pattern, replacement, text)
    for word in load_vocabulary():               # normalise known-term casing
        # A function replacement, so a learned word is inserted literally: as a
        # template string, a backslash in it would raise and lose the dictation.
        text = re.sub(r'(?i)\b' + re.escape(word) + r'\b', lambda _: word, text)

    text = text.strip()
    if wrap_code:
        text = f"`{text}`"
    if lead_bullet:
        text = "• " + text
    elif not lead_newline and text and not wrap_code:
        text = " " + text                        # keep spacing against the previous word

    return text, lead_newline, end_enter


def paste_text(text, press_enter=False):
    """Paste `text` at the cursor through the clipboard, then restore the clipboard."""
    # Hold the clipboard for the whole save/paste/restore cycle so the reader cannot
    # copy a selection into the middle of it, in either process layout.
    with clipboard_lock():
        saved_clipboard = pyperclip.paste()
        pyperclip.copy(text)
        time.sleep(0.04)
        keyboard.send('ctrl+v')
        # Give slow apps time to read the clipboard before we restore it — restoring
        # too early makes them paste the *old* clipboard contents instead.
        time.sleep(0.15)
        if press_enter:
            keyboard.send('enter')
        pyperclip.copy(saved_clipboard)          # restore the user's clipboard


def inject_text(text):
    """Apply spoken macros/punctuation, then paste the text at the cursor."""
    if not text:
        return
    text, lead_newline, end_enter = apply_macros(text)

    if lead_newline:
        keyboard.send('shift+enter')
        time.sleep(0.02)

    logging.info(f"Injecting text via clipboard paste: {text!r}")
    paste_text(text, press_enter=end_enter)

# =====================================================================
# RECORDING WORKER (one per capture, runs off the hotkey thread)
# =====================================================================
def read_clipboard_context():
    """The clipboard, minus URLs and capped, as background for the Polish prompt."""
    try:
        # Under the lock, so an injection still in flight is not mistaken for context.
        with clipboard_lock():
            return re.sub(URL_PATTERN, '', pyperclip.paste())[:500]
    except Exception:
        return ""


def process_recording(capture):
    """Open the mic, capture until stopped, then transcribe → refine → inject.

    Everything this recording needs travels in `capture`, because the next recording
    can start while this one is still closing its microphone or transcribing."""
    mode = capture.mode
    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
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


def transcribe_and_inject(audio, mode, context):
    """Stages 2-4 for one captured clip: transcribe, refine, paste."""
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak                     # normalise to full scale
    sf.write(TEMP_AUDIO_FILE, audio, SAMPLE_RATE)

    ui.update_console_title("DECODING")
    started = time.time()
    text, lang = transcribe_clip(MODES[mode]["lang"])
    # The speed figure docs/HARDWARE.md tunes against: seconds spent per clip.
    took = time.time() - started
    logging.info(f"Transcription result (mode={mode}, lang={lang}, "
                 f"{took:.2f}s for {len(audio) / SAMPLE_RATE:.1f}s of audio): {text!r}")
    if os.path.exists(TEMP_AUDIO_FILE):
        os.remove(TEMP_AUDIO_FILE)

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

# =====================================================================
# HOTKEY HANDLERS
# =====================================================================
def on_record_hotkey(mode_name):
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

def on_cancel_hotkey():
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

def wait_for_release(hotkey, timeout=1.0):
    """Wait (briefly) until every key in `hotkey` ("shift+f3") is up, so keys we send
    next are not combined with ones the user is still holding."""
    keys = [k.strip() for k in hotkey.split("+")]
    deadline = time.monotonic() + timeout
    while any(keyboard.is_pressed(k) for k in keys) and time.monotonic() < deadline:
        time.sleep(0.02)


def correct_current_line():
    """Shift+F3 — grab the current line, fix it via the LLM, paste it back."""
    if is_recording():
        return
    print(f"\n{ui.C_ACCENT}⚡ Running contextual line refinement...{ui.C_RESET}")
    ui.play_tone("start", ENABLE_AUDIO_CHIMES)
    # Still holding Shift from Shift+F3 would turn the Ctrl+C below into Ctrl+Shift+C
    # (DevTools in a browser) — wait for the keys to come up first.
    wait_for_release(HOTKEYS["fix"])

    # Copy the line under the clipboard lock, like every other clipboard sequence,
    # so the reader cannot copy a selection in between. The lock is not held across
    # the LLM call below, which can take seconds.
    with clipboard_lock():
        saved_clipboard = pyperclip.paste()
        pyperclip.copy("")                       # so a failed copy reads as empty, not as stale text
        keyboard.send('shift+home'); time.sleep(0.05)
        keyboard.send('ctrl+c');     time.sleep(0.05)
        target_text = pyperclip.paste().strip()
        pyperclip.copy(saved_clipboard)

    if not target_text:
        ui.play_tone("empty", ENABLE_AUDIO_CHIMES)
        return

    lang = "ar" if ARABIC_LETTERS.search(target_text) else "en"
    fixed = ask_ollama(target_text, None, personas.LINE_CORRECTION_PROMPT)
    if fixed is not None:
        fixed = checked_ai_output(fixed, target_text, lang)
    if fixed and fixed != target_text:
        print(f"✨ Optimized: '{ui.C_GOOD}{fixed}{ui.C_RESET}'")
        paste_text(fixed)                        # replaces the still-selected line
        ui.play_tone("correction", ENABLE_AUDIO_CHIMES)
        log_to_history(fixed, "line_fix")
    else:
        keyboard.send('right')                   # deselect, leave the line untouched
        ui.play_tone("stop", ENABLE_AUDIO_CHIMES)

def _run_async(fn):
    """Wrap a hotkey handler so it runs on its own daemon thread. Heavy handlers
    (LLM calls, key-sending) must never run on the keyboard listener thread —
    blocking it freezes the whole keyboard until they return, which is what forced
    the app restarts on Ctrl+F10/F11. Failures are logged, not just printed."""
    def run():
        try:
            fn()
        except Exception:
            logging.error(f"{fn.__name__} failed: {traceback.format_exc()}")
            print(f"{ui.C_ERR}❌ {fn.__name__} failed — details in flow_debug.log.{ui.C_RESET}")
            ui.update_console_title("ONLINE")
    return lambda: threading.Thread(target=run, daemon=True).start()

# =====================================================================
# ENTRY POINT
# =====================================================================
def boot():
    """Load the model and get the dictation half ready. Shared by both entry points
    (this file standalone, and the supervisor in zero_flow.py)."""
    global model

    ui.update_console_title("INITIALIZING HARDWARE")
    # Clear any stale recording flag left behind if a previous run was force-killed
    # mid-capture — otherwise a running reader would keep refusing to speak.
    signals.set_recording(False)
    # Load the AI model alongside Whisper rather than on the first Polish (3-12 s).
    threading.Thread(target=warm_up_llm, daemon=True).start()
    model = load_whisper_model()
    cap_history_file()
    ui.update_console_title("ONLINE")


def register_hotkeys():
    """Bind the dictation keys. Shared by both entry points."""
    # Record modes (F5–F10). suppress=True consumes the key so it never reaches the
    # focused app (e.g. F5 = browser refresh). The lambda captures each mode name.
    for mode in MODES:
        keyboard.add_hotkey(HOTKEYS[mode], (lambda m: lambda: on_record_hotkey(m))(mode), suppress=True)

    # Action keys do heavy work (LLM calls, key-sending), so dispatch each to a worker
    # thread — never block the keyboard listener (that froze the whole keyboard).
    keyboard.add_hotkey(HOTKEYS["fix"],         _run_async(correct_current_line), suppress=True)
    keyboard.add_hotkey(HOTKEYS["maintenance"], _run_async(run_memory_maintenance), suppress=True)
    keyboard.add_hotkey(HOTKEYS["purge"],       _run_async(purge_diagnostic_files), suppress=True)
    keyboard.add_hotkey(HOTKEYS["panic"],       on_cancel_hotkey)


def main():
    boot()
    ui.print_boot_sequence(get_ollama_model(), HOTKEYS,
                           speech=f"Whisper {WHISPER_MODEL_NAME} · {model_runtime}")
    ui.show_toast("🚀 Zero- Flow Online", "Background engine is active and listening.", ENABLE_TOASTS)
    ui.setup_system_tray()
    ui.set_window_icon()
    register_hotkeys()
    keyboard.wait()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.critical(f"Fatal engine crash: {traceback.format_exc()}")
