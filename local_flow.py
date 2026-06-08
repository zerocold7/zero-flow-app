"""
Zero- Flow Engine — local, bilingual (Arabic / English) voice dictation for Windows 11.

Pipeline:  hotkey  →  record mic  →  faster-whisper transcribe  →  (optional Ollama
refine)  →  paste into the focused app.

Modes (one hotkey each):
    raw       (F9)   transcribe and inject exactly as spoken
    english   (F8)   same, but force English (skip language auto-detect)
    polish    (F10)  transcribe, then clean up via the local LLM (same language)
    translate (F11)  transcribe, then translate Arabic⇄English via the local LLM
    fix       (Ctrl+F10)  rewrite the current line via the LLM
    maintenance (Ctrl+F11) prune the learned-vocabulary file via the LLM
    cancel    (Esc)  cancel an in-progress recording

See ARCHITECTURE.md for the full design rationale.
"""
import os
import sys
import time
import queue
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
import requests
from faster_whisper import WhisperModel
from dotenv import load_dotenv

try:
    import personas
    import engine_ui as ui
except ImportError as e:
    print(f"❌ Critical error: Missing local module: {e}")
    sys.exit(1)

# =====================================================================
# PATHS & LOGGING
# =====================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VOCAB_CACHE_FILE = os.path.join(BASE_DIR, "flow_vocabulary.txt")
TEMP_AUDIO_FILE = os.path.join(BASE_DIR, "flow_capture.wav")
HISTORY_FILE = os.path.join(BASE_DIR, "flow_history.md")
LOG_FILE = os.path.join(BASE_DIR, "flow_debug.log")

logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logging.info("=== Zero- Core Application Boot Sequence Initiated ===")

load_dotenv()

# =====================================================================
# CONFIGURATION
# =====================================================================
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL_NAME", "large-v3")
OLLAMA_HOST_URL    = os.getenv("OLLAMA_HOST_URL", "http://127.0.0.1:11434/api/generate")
FALLBACK_LLM       = os.getenv("FALLBACK_LLM", "gemma2:27b")
SAMPLE_RATE        = int(os.getenv("SAMPLE_RATE", 16000))
CHANNELS           = int(os.getenv("CHANNELS", 1))

HOTKEYS = {
    "raw":         os.getenv("HOTKEY_RAW", "f9"),
    "polish":      os.getenv("HOTKEY_POLISH", "f10"),
    "translate":   os.getenv("HOTKEY_TRANSLATE", "f11"),
    "english":     os.getenv("HOTKEY_ENGLISH", "f8"),
    "fix":         os.getenv("HOTKEY_FIX", "ctrl+f10"),
    "maintenance": os.getenv("HOTKEY_MAINTENANCE", "ctrl+f11"),
    "panic":       os.getenv("HOTKEY_PANIC", "esc"),
}

ENABLE_AUDIO_CHIMES = os.getenv("ENABLE_AUDIO_CHIMES", "True").lower() in ('true', '1', 't')
ENABLE_TOASTS       = os.getenv("ENABLE_TOAST_NOTIFICATIONS", "True").lower() in ('true', '1', 't')

# This engine only ever speaks Arabic or English; anything else is a misdetection.
SUPPORTED_LANGS = ("ar", "en")
# Clips shorter than this (after capture) are dropped — they only ever produce
# Whisper hallucinations, never real words.
MIN_CLIP_SECONDS = 0.4

LEARN_PATTERN = re.compile(r'\[LEARN:\s*(.*?)\]')
URL_PATTERN = re.compile(r'https?://\S+|www\.\S+')

# =====================================================================
# RUNTIME STATE (set in main / mutated by the hotkey + worker threads)
# =====================================================================
model = None              # faster-whisper model, loaded in main()
OLLAMA_MODEL = None       # discovered LLM name, set in main()
recording = False         # True while the mic stream is open
cancel_flag = False       # set by Esc to discard the current capture
active_mode = "raw"       # which mode the in-flight recording belongs to
clipboard_context = ""    # clipboard snapshot, fed to the LLM in Polish mode
audio_queue = queue.Queue()

# =====================================================================
# HARDWARE / SERVICE DISCOVERY
# =====================================================================
def load_whisper_model():
    """Load faster-whisper on the GPU, verifying with a real inference so a missing
    CUDA library falls back to CPU at boot instead of crashing mid-dictation."""
    # Make any pip-installed CUDA DLLs (nvidia-cublas-cu12 / nvidia-cudnn-cu12) findable.
    for entry in sys.path:
        for lib in ("cublas", "cudnn"):
            bin_dir = os.path.join(entry, "nvidia", lib, "bin")
            if os.path.isdir(bin_dir):
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                if hasattr(os, "add_dll_directory"):
                    os.add_dll_directory(bin_dir)
    try:
        m = WhisperModel(WHISPER_MODEL_NAME, device="cuda", compute_type="float16")
        # CTranslate2 loads the CUDA libs lazily on first inference, so force a tiny
        # real decode now — any GPU failure surfaces here and falls back cleanly.
        list(m.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), vad_filter=False)[0])
        logging.info("Whisper model active on CUDA (float16).")
        return m
    except Exception as e:
        logging.warning(f"CUDA unavailable ({e}); falling back to CPU (int8).")
        m = WhisperModel(WHISPER_MODEL_NAME, device="cpu", compute_type="int8")
        logging.info("Whisper model active on CPU (int8).")
        return m

def discover_ollama_model():
    """Bind to whatever model the local Ollama instance is currently serving."""
    try:
        tags_url = OLLAMA_HOST_URL.replace("/api/generate", "/api/tags")
        response = requests.get(tags_url, timeout=2)
        if response.status_code == 200 and response.json().get("models"):
            return response.json()["models"][0]["name"]
    except Exception:
        pass
    return FALLBACK_LLM

# =====================================================================
# VOCABULARY, HISTORY & LLM
# =====================================================================
def load_vocabulary():
    """Base vocabulary plus any words the LLM has learned over time."""
    vocab = set(personas.BASE_VOCABULARY)
    if os.path.exists(VOCAB_CACHE_FILE):
        try:
            with open(VOCAB_CACHE_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        vocab.add(line.strip())
        except Exception:
            pass
    return list(vocab)

def log_to_history(text, mode):
    if not text:
        return
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] [{mode.upper()}]\n{text}\n\n")
    except Exception as e:
        logging.error(f"History write fail: {e}")

def query_ollama(raw_text, context_text, instruction):
    """Send text to the local LLM with a task instruction; return its output (or
    the original text on failure). Honours an inline `[LEARN: word]` request."""
    prompt = f"{instruction}\n\n"
    if context_text:
        prompt += f"Context Window Data:\n{context_text}\n\n"
    prompt += f"Input Raw String: {raw_text}\nOutput String:"

    ui.start_processing_spinner("AI Processing")
    try:
        response = requests.post(
            OLLAMA_HOST_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.2}},
            timeout=15.0,
        )
        ui.stop_processing_spinner()
        if response.status_code == 200:
            output = response.json().get("response", raw_text).strip()
            return _absorb_learned_word(output)
    except Exception:
        ui.stop_processing_spinner()
        ui.show_toast("⚠️ LLM Offline", "Ollama API failed to respond.", ENABLE_TOASTS)
    return raw_text

def _absorb_learned_word(output):
    """If the LLM tagged a new term as `[LEARN: word]`, persist it and strip the tag."""
    match = LEARN_PATTERN.search(output)
    if not match:
        return output
    word = match.group(1).strip()
    if word and word not in load_vocabulary():
        with open(VOCAB_CACHE_FILE, "a", encoding="utf-8") as f:
            f.write(f"{word}\n")
        ui.show_toast("🧠 Learned New Word", f"Added '{word}'", ENABLE_TOASTS)
    return LEARN_PATTERN.sub('', output).strip()

def run_memory_maintenance():
    """Ctrl+F11 — let the LLM dedupe / clean the learned-vocabulary file."""
    if recording:
        return
    print(f"\n{ui.C_WARN}🧹 AI Janitor: Analyzing and pruning vocabulary memory...{ui.C_RESET}")
    ui.show_toast("🧹 Memory Maintenance", "AI is optimizing your vocabulary files.", ENABLE_TOASTS)
    ui.update_console_title("MAINTENANCE RUNNING")

    current_vocab = "\n".join(load_vocabulary())
    cleaned = query_ollama(current_vocab, None, personas.MEMORY_MAINTENANCE_PROMPT)
    if cleaned:
        try:
            with open(VOCAB_CACHE_FILE, "w", encoding="utf-8") as f:
                f.write(cleaned + "\n")
            print(f"{ui.C_GOOD}✅ Vocabulary successfully compressed and organized.{ui.C_RESET}")
            ui.show_toast("✅ Maintenance Complete", "Memory files pruned successfully.", ENABLE_TOASTS)
            ui.play_tone("clean", ENABLE_AUDIO_CHIMES)
        except Exception:
            print(f"{ui.C_ERR}❌ Failed to write cleaned memory.{ui.C_RESET}")
    ui.update_console_title("ONLINE")

# =====================================================================
# AUDIO CAPTURE & TRANSCRIPTION
# =====================================================================
def audio_callback(indata, frames, time_info, status):
    """sounddevice callback: buffer audio and draw a live level meter."""
    if not recording:
        return
    audio_queue.put(indata.copy())
    level = int(min(np.linalg.norm(indata) * 10, 20))
    bars = "|" * level + " " * (20 - level)
    sys.stdout.write(f"\r{ui.C_ACCENT}[{ui.C_GOOD}{bars}{ui.C_ACCENT}] Capturing Voice Data...{ui.C_RESET}")
    sys.stdout.flush()

def drain_audio_queue():
    """Collect everything captured so far into one array, or None if empty."""
    chunks = []
    while not audio_queue.empty():
        chunks.append(audio_queue.get())
    return np.concatenate(chunks, axis=0) if chunks else None

def transcribe_clip(force_english):
    """Decode TEMP_AUDIO_FILE → (text, language).

    Auto-detects the language unless force_english is set. If auto-detect returns
    a language we don't support (e.g. Malay/Hebrew = a misdetection that produces
    gibberish), it re-decodes forcing whichever of Arabic/English scored higher.
    """
    # Only the vocabulary terms are used as a hint — no English framing sentence,
    # which would otherwise bias the decoder into writing Arabic speech as English.
    vocab_hint = ", ".join(load_vocabulary()) or None

    def decode(language):
        # condition_on_previous_text=False prevents repetition-loop hallucinations;
        # beam_size=5 gives steadier decoding on short clips.
        segments, info = model.transcribe(
            TEMP_AUDIO_FILE, beam_size=5, vad_filter=True,
            condition_on_previous_text=False, language=language,
            initial_prompt=vocab_hint,
        )
        return "".join(s.text for s in segments).strip(), info

    try:
        text, info = decode("en" if force_english else None)
        lang = info.language
        if not force_english and lang not in SUPPORTED_LANGS:
            probs = dict(getattr(info, "all_language_probs", None) or [])
            lang = "ar" if probs.get("ar", 0) >= probs.get("en", 0) else "en"
            logging.warning(f"Detected non-ar/en language — re-decoding as '{lang}'.")
            text, _ = decode(lang)
        return text, lang
    except Exception as e:
        logging.error(f"Whisper transcription failed: {e}")
        return "", None

# =====================================================================
# TEXT REFINEMENT & INJECTION
# =====================================================================
def refine_text(text, lang):
    """Apply the active mode's AI step. Raw / English pass straight through."""
    if active_mode == "polish":
        ui.update_console_title("OLLAMA PROCESSING")
        out = query_ollama(text, clipboard_context, personas.STANDARD_SYSTEM_PROMPT)
        print(f"✨ Polished: {ui.C_GOOD}{out}{ui.C_RESET}")
        ui.show_toast("✨ Polish Complete", "Cleaned prose injected.", ENABLE_TOASTS)
        ui.play_tone("success_polish", ENABLE_AUDIO_CHIMES)
        return out

    if active_mode == "translate":
        ui.update_console_title("OLLAMA TRANSLATING")
        # Translate to the opposite of the detected language.
        if lang == "ar":
            direction, prompt = "AR→EN", personas.TRANSLATE_TO_EN_PROMPT
        else:
            direction, prompt = "EN→AR", personas.TRANSLATE_TO_AR_PROMPT
        out = query_ollama(text, None, prompt)
        print(f"🌐 Translated [{direction}]: {ui.C_WARN}{out}{ui.C_RESET}")
        ui.show_toast("🌐 Translation Complete", f"{direction} prose injected.", ENABLE_TOASTS)
        ui.play_tone("success_translate", ENABLE_AUDIO_CHIMES)
        return out

    ui.play_tone("success_raw", ENABLE_AUDIO_CHIMES)
    return text

def inject_text(text):
    """Apply spoken macros/punctuation, then paste the text at the cursor."""
    if not text:
        return
    macros = personas.VOICE_MACROS
    lowered = text.lower().strip()
    lead_newline = any(lowered.startswith(t) for t in macros["new_line"])
    lead_bullet  = any(lowered.startswith(t) for t in macros["bullet"])
    wrap_code    = any(lowered.startswith(t) for t in macros["code_block"])
    end_enter    = any(lowered.endswith(t) for t in macros["press_enter"])

    # Strip a leading macro keyword ("new line", "bullet", "format code", …).
    for group in macros.values():
        for token in group:
            text = re.sub(r'(?i)^' + re.escape(token), '', text, count=1)
    if end_enter:
        text = text.rsplit(' ', 1)[0] if ' ' in text else text

    for pattern, replacement in personas.PUNCTUATION_MAP.items():
        text = re.sub(pattern, replacement, text)
    for word in load_vocabulary():               # normalise known-term casing
        text = re.sub(r'(?i)\b' + re.escape(word) + r'\b', word, text)

    text = text.strip()
    if wrap_code:
        text = f"`{text}`"
    if lead_bullet:
        text = "• " + text

    if lead_newline:
        keyboard.send('shift+enter')
        time.sleep(0.02)
    elif text and not text.startswith(" ") and not lead_bullet and not wrap_code:
        text = " " + text

    logging.info(f"Injecting text via clipboard paste: {text!r}")
    saved_clipboard = pyperclip.paste()
    pyperclip.copy(text)
    time.sleep(0.04)
    keyboard.send('ctrl+v')
    time.sleep(0.04)
    if end_enter:
        keyboard.send('enter')
    pyperclip.copy(saved_clipboard)              # restore the user's clipboard

# =====================================================================
# RECORDING WORKER (one per capture, runs off the hotkey thread)
# =====================================================================
def process_recording():
    """Open the mic, capture until stopped, then transcribe → refine → inject."""
    global recording, cancel_flag
    audio_queue.queue.clear()

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                            callback=audio_callback, dtype='float32'):
            while recording:
                sd.sleep(40)
    except Exception as e:
        logging.error(f"Audio InputStream failed to open: {e}")
        recording = False
        return

    sys.stdout.write("\r" + " " * 50 + "\r")     # wipe the live meter line

    if cancel_flag:
        cancel_flag = False
        print(f"{ui.C_ERR}🛑 Audio flushed. Processing skipped.{ui.C_RESET}")
        ui.update_console_title("ONLINE")
        return

    audio = drain_audio_queue()
    if audio is None:
        ui.update_console_title("ONLINE")
        return
    if len(audio) / SAMPLE_RATE < MIN_CLIP_SECONDS:
        logging.info("Recording too short (<0.4s) — skipped to avoid hallucination on near-silence.")
        ui.play_tone("empty", ENABLE_AUDIO_CHIMES)
        ui.update_console_title("ONLINE")
        return

    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak                     # normalise to full scale
    sf.write(TEMP_AUDIO_FILE, audio, SAMPLE_RATE)

    ui.update_console_title("DECODING")
    text, lang = transcribe_clip(active_mode == "english")
    logging.info(f"Transcription result (mode={active_mode}, lang={lang}): {text!r}")
    if os.path.exists(TEMP_AUDIO_FILE):
        os.remove(TEMP_AUDIO_FILE)

    if not text:
        logging.info("Empty transcription — nothing injected (silence / VAD dropped all audio).")
        ui.play_tone("empty", ENABLE_AUDIO_CHIMES)
        ui.update_console_title("ONLINE")
        return

    print(f"📝 Raw: {text}")
    text = refine_text(text, lang)
    inject_text(text)
    log_to_history(text, active_mode)
    ui.update_console_title("ONLINE")

# =====================================================================
# HOTKEY HANDLERS
# =====================================================================
def on_record_hotkey(mode_selection):
    """A record key (F8–F11) was pressed: start a capture, or stop the active one."""
    global recording, active_mode, clipboard_context, cancel_flag

    if recording:
        # Any record key stops the capture. We do NOT switch modes mid-recording —
        # that silent switch (e.g. tapping F11 during a raw F9 clip) was the cause
        # of surprise translations. The mode is locked in at the start.
        recording = False
        ui.set_tray_state(False)
        ui.play_tone("stop", ENABLE_AUDIO_CHIMES)
        return

    cancel_flag = False
    try:
        clipboard_context = re.sub(URL_PATTERN, '', pyperclip.paste())[:500]
    except Exception:
        clipboard_context = ""

    active_mode = mode_selection
    recording = True
    ui.set_tray_state(True)
    print(f"\n{ui.C_ACCENT}🔴 [{active_mode.upper()}] Capturing audio...{ui.C_RESET}")
    ui.play_tone("start", ENABLE_AUDIO_CHIMES)
    threading.Thread(target=process_recording).start()

def on_cancel_hotkey():
    """Esc — cancel an in-progress recording. (Does nothing when idle, so Esc keeps
    working normally in your apps; use the app's own Ctrl+Z to undo an injection.)"""
    global recording, cancel_flag
    if recording:
        cancel_flag = True
        recording = False
        ui.set_tray_state(False)
        print(f"\n{ui.C_ERR}🛑 Recording cancelled.{ui.C_RESET}")
        ui.play_tone("cancel", ENABLE_AUDIO_CHIMES)

def correct_current_line():
    """Ctrl+F10 — grab the current line, fix it via the LLM, paste it back."""
    if recording:
        return
    print(f"\n{ui.C_ACCENT}⚡ Running contextual line refinement...{ui.C_RESET}")
    ui.play_tone("start", ENABLE_AUDIO_CHIMES)

    saved_clipboard = pyperclip.paste()
    keyboard.send('shift+home'); time.sleep(0.05)
    keyboard.send('ctrl+c');     time.sleep(0.05)

    target_text = pyperclip.paste().strip()
    if not target_text or target_text == saved_clipboard:
        ui.play_tone("empty", ENABLE_AUDIO_CHIMES)
        return

    fixed = query_ollama(target_text, None, personas.LINE_CORRECTION_PROMPT)
    if fixed and fixed != target_text:
        print(f"✨ Optimized: '{ui.C_GOOD}{fixed}{ui.C_RESET}'")
        pyperclip.copy(fixed); time.sleep(0.03)
        keyboard.send('ctrl+v'); time.sleep(0.03)
        ui.play_tone("correction", ENABLE_AUDIO_CHIMES)
        log_to_history(fixed, "line_fix")
    else:
        keyboard.send('right')                   # deselect, leave the line untouched
        ui.play_tone("stop", ENABLE_AUDIO_CHIMES)

    pyperclip.copy(saved_clipboard)

# =====================================================================
# ENTRY POINT
# =====================================================================
def main():
    global model, OLLAMA_MODEL

    ui.update_console_title("INITIALIZING HARDWARE")
    OLLAMA_MODEL = discover_ollama_model()
    model = load_whisper_model()

    ui.update_console_title("ONLINE")
    ui.print_boot_sequence(OLLAMA_MODEL, HOTKEYS)
    ui.show_toast("🚀 Zero- Flow Online", "Background engine is active and listening.", ENABLE_TOASTS)
    ui.setup_system_tray()
    ui.set_window_icon()

    # suppress=True consumes the record keys so they never reach the focused app
    # (F11=fullscreen, F10=menus). Esc is left un-suppressed so it works normally.
    keyboard.add_hotkey(HOTKEYS["raw"],         lambda: on_record_hotkey("raw"), suppress=True)
    keyboard.add_hotkey(HOTKEYS["polish"],      lambda: on_record_hotkey("polish"), suppress=True)
    keyboard.add_hotkey(HOTKEYS["translate"],   lambda: on_record_hotkey("translate"), suppress=True)
    keyboard.add_hotkey(HOTKEYS["english"],     lambda: on_record_hotkey("english"), suppress=True)
    keyboard.add_hotkey(HOTKEYS["fix"],         correct_current_line, suppress=True)
    keyboard.add_hotkey(HOTKEYS["maintenance"], run_memory_maintenance, suppress=True)
    keyboard.add_hotkey(HOTKEYS["panic"],       on_cancel_hotkey)
    keyboard.wait()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.critical(f"Fatal Engine Crash: {traceback.format_exc()}")
