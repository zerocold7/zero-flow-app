import os
import sys
import time
import queue
import threading
import ctypes
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

# Import custom modules
try:
    import personas
    import engine_ui as ui
except ImportError as e:
    print(f"❌ Critical error: Missing local module: {e}")
    sys.exit(1)

# =====================================================================
# PATH RESOLUTION & LOGGING
# =====================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VOCAB_CACHE_FILE = os.path.join(BASE_DIR, "flow_vocabulary.txt")
TEMP_AUDIO_FILE = os.path.join(BASE_DIR, "flow_capture.wav")
HISTORY_FILE = os.path.join(BASE_DIR, "flow_history.md")
LOG_FILE = os.path.join(BASE_DIR, "flow_debug.log")

logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.info("=== Zero- Core Application Boot Sequence Initiated ===")

load_dotenv()

# =====================================================================
# CONFIGURATION
# =====================================================================
WHISPER_MODEL_NAME  = os.getenv("WHISPER_MODEL_NAME", "large-v3")    
OLLAMA_HOST_URL     = os.getenv("OLLAMA_HOST_URL", "http://127.0.0.1:11434/api/generate")
FALLBACK_LLM        = os.getenv("FALLBACK_LLM", "gemma2:27b")
SAMPLE_RATE         = int(os.getenv("SAMPLE_RATE", 16000))
CHANNELS            = int(os.getenv("CHANNELS", 1))

HOTKEYS = {
    "raw": os.getenv("HOTKEY_RAW", "f9"),
    "polish": os.getenv("HOTKEY_POLISH", "f10"),
    "translate": os.getenv("HOTKEY_TRANSLATE", "f11"),
    "english": os.getenv("HOTKEY_ENGLISH", "f8"),
    "fix": os.getenv("HOTKEY_FIX", "ctrl+f10"),
    "maintenance": os.getenv("HOTKEY_MAINTENANCE", "ctrl+f11"),
    "panic": os.getenv("HOTKEY_PANIC", "esc")
}

ENABLE_AUDIO_CHIMES = os.getenv("ENABLE_AUDIO_CHIMES", "True").lower() in ('true', '1', 't')
ENABLE_TOASTS       = os.getenv("ENABLE_TOAST_NOTIFICATIONS", "True").lower() in ('true', '1', 't')

def get_active_ollama_model():
    try:
        response = requests.get(OLLAMA_HOST_URL.replace("/api/generate", "/api/tags"), timeout=2)
        if response.status_code == 200 and response.json().get("models"):
            return response.json()["models"][0]["name"]
    except Exception: pass
    return FALLBACK_LLM

OLLAMA_MODEL = get_active_ollama_model()
LEARN_PATTERN = re.compile(r'\[LEARN:\s*(.*?)\]')
URL_PATTERN = re.compile(r'https?://\S+|www\.\S+')

# Context Containers
recording = False
cancel_flag = False
audio_queue = queue.Queue()
active_mode = "raw" 
clipboard_context = ""

# =====================================================================
# INITIALIZATION
# =====================================================================
ui.update_console_title("INITIALIZING HARDWARE")
for bp in sys.path:
    for lib in ["cublas", "cudnn"]:
        bin_path = os.path.join(bp, "nvidia", lib, "bin")
        if os.path.exists(bin_path):
            os.environ["PATH"] = bin_path + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, 'add_dll_directory'): os.add_dll_directory(bin_path)

try:
    model = WhisperModel(WHISPER_MODEL_NAME, device="cuda", compute_type="float16")
    # CTranslate2 loads the CUDA libs lazily on the first inference, so a missing
    # cublas/cudnn does NOT raise here — it crashes mid-dictation and (previously)
    # got swallowed into empty text. Force a tiny real inference now so any GPU
    # failure surfaces at boot and falls back to CPU cleanly.
    list(model.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), vad_filter=False)[0])
    logging.info("Whisper model active on CUDA (float16).")
except Exception as e:
    logging.warning(f"CUDA unavailable ({e}); falling back to CPU (int8).")
    model = WhisperModel(WHISPER_MODEL_NAME, device="cpu", compute_type="int8")
    logging.info("Whisper model active on CPU (int8).")

ui.update_console_title("ONLINE")
ui.print_boot_sequence(OLLAMA_MODEL, HOTKEYS)
ui.show_toast("🚀 Zero- Flow Online", "Background engine is active and listening.", ENABLE_TOASTS)
ui.setup_system_tray()
ui.set_window_icon()

# =====================================================================
# SELF-HEALING MEMORY & DATA PIPELINES
# =====================================================================
def log_to_history(text, mode):
    if not text: return
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] [{mode.upper()}]\n{text}\n\n")
    except Exception as e: logging.error(f"History write fail: {e}")

def load_adapted_vocabulary():
    vocab_set = set(personas.BASE_VOCABULARY)
    if os.path.exists(VOCAB_CACHE_FILE):
        try:
            with open(VOCAB_CACHE_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip(): vocab_set.add(line.strip())
        except Exception: pass
    return list(vocab_set)

def query_local_ollama(raw_text, context_text, specialized_instruction):
    prompt_payload = f"{specialized_instruction}\n\n"
    if context_text: prompt_payload += f"Context Window Data:\n{context_text}\n\n"
    prompt_payload += f"Input Raw String: {raw_text}\nOutput String:"
    
    ui.start_processing_spinner("AI Processing")
    try:
        response = requests.post(OLLAMA_HOST_URL, json={"model": OLLAMA_MODEL, "prompt": prompt_payload, "stream": False, "options": {"temperature": 0.2}}, timeout=15.0)
        ui.stop_processing_spinner()
        
        if response.status_code == 200:
            output = response.json().get("response", raw_text).strip()
            match = LEARN_PATTERN.search(output)
            if match:
                word = match.group(1).strip()
                if word not in load_adapted_vocabulary():
                    with open(VOCAB_CACHE_FILE, "a", encoding="utf-8") as f: f.write(f"{word}\n")
                    ui.show_toast("🧠 Learned New Word", f"Added '{word}'", ENABLE_TOASTS)
                output = LEARN_PATTERN.sub('', output).strip()
            return output
    except Exception:
        ui.stop_processing_spinner()
        ui.show_toast("⚠️ LLM Offline", "Ollama API failed to respond.", ENABLE_TOASTS)
    return raw_text

def execute_memory_maintenance():
    if recording: return
    print(f"\n{ui.C_WARN}🧹 AI Janitor: Analyzing and pruning vocabulary memory...{ui.C_RESET}")
    ui.show_toast("🧹 Memory Maintenance", "AI is optimizing your vocabulary files.", ENABLE_TOASTS)
    ui.update_console_title("MAINTENANCE RUNNING")
    
    current_vocab = load_adapted_vocabulary()
    raw_vocab_string = "\n".join(current_vocab)
    
    cleaned_vocab_string = query_local_ollama(raw_vocab_string, None, personas.MEMORY_MAINTENANCE_PROMPT)
    
    if cleaned_vocab_string:
        try:
            with open(VOCAB_CACHE_FILE, "w", encoding="utf-8") as f:
                f.write(cleaned_vocab_string + "\n")
            print(f"{ui.C_GOOD}✅ Vocabulary successfully compressed and organized.{ui.C_RESET}")
            ui.show_toast("✅ Maintenance Complete", "Memory files pruned successfully.", ENABLE_TOASTS)
            ui.play_tone("clean", ENABLE_AUDIO_CHIMES)
        except Exception:
            print(f"{ui.C_ERR}❌ Failed to write cleaned memory.{ui.C_RESET}")
    ui.update_console_title("ONLINE")

# =====================================================================
# AUDIO CAPTURE & INJECTION ENGINE
# =====================================================================
def audio_callback(indata, frames, time_info, status):
    if recording:
        audio_queue.put(indata.copy())
        vol = np.linalg.norm(indata) * 10
        bars = "|" * int(min(vol, 20))
        spaces = " " * (20 - len(bars))
        sys.stdout.write(f"\r{ui.C_ACCENT}[{ui.C_GOOD}{bars}{spaces}{ui.C_ACCENT}] Capturing Voice Data...{ui.C_RESET}")
        sys.stdout.flush()

def execute_smart_injection(text):
    if not text: return
    lower_check, text_stripped = text.lower().strip(), text.strip()
    
    leading_newline = any(lower_check.startswith(t) for t in personas.VOICE_MACROS["new_line"])
    leading_bullet = any(lower_check.startswith(t) for t in personas.VOICE_MACROS["bullet"])
    wrap_code_block = any(lower_check.startswith(t) for t in personas.VOICE_MACROS["code_block"])
    press_enter_at_end = any(lower_check.endswith(t) for t in personas.VOICE_MACROS["press_enter"])

    for macro_group in personas.VOICE_MACROS.values():
        for token in macro_group:
            text = re.sub(r'(?i)^' + re.escape(token), '', text, count=1)
    
    if press_enter_at_end: text = text.rsplit(' ', 1)[0] if ' ' in text else text

    for pattern, replacement in personas.PUNCTUATION_MAP.items():
        text = re.sub(pattern, replacement, text)
    for word in load_adapted_vocabulary():
        text = re.sub(r'(?i)\b' + re.escape(word) + r'\b', word, text)

    text = text.strip()
    if wrap_code_block: text = f"`{text}`"
    if leading_bullet: text = "• " + text
        
    if leading_newline: keyboard.send('shift+enter'); time.sleep(0.02)
    elif text and not text.startswith(" ") and not leading_bullet and not wrap_code_block:
        text = " " + text

    logging.info(f"Injecting text via clipboard paste: {text!r}")
    original_clipboard = pyperclip.paste()
    pyperclip.copy(text)
    time.sleep(0.04)
    keyboard.send('ctrl+v')
    time.sleep(0.04)
    if press_enter_at_end: keyboard.send('enter')
    pyperclip.copy(original_clipboard)

def core_processing_engine():
    global recording, cancel_flag
    audio_queue.queue.clear()
    
    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, callback=audio_callback, dtype='float32'):
            while recording: sd.sleep(40)
    except Exception as e:
        logging.error(f"Audio InputStream failed to open: {e}")
        recording = False
        return
            
    sys.stdout.write("\r" + " " * 50 + "\r")
    
    if cancel_flag:
        print(f"{ui.C_ERR}🛑 Audio flushed. Processing skipped.{ui.C_RESET}")
        cancel_flag = False; ui.update_console_title("ONLINE"); return

    audio_chunks = []
    while not audio_queue.empty(): audio_chunks.append(audio_queue.get())
    if not audio_chunks: ui.update_console_title("ONLINE"); return

    audio_np = np.concatenate(audio_chunks, axis=0)
    if len(audio_np) / SAMPLE_RATE < 0.4:
        logging.info("Recording too short (<0.4s) — skipped to avoid hallucination on near-silence.")
        ui.play_tone("empty", ENABLE_AUDIO_CHIMES); ui.update_console_title("ONLINE"); return
    max_val = np.max(np.abs(audio_np))
    if max_val > 0: audio_np = audio_np / max_val
        
    sf.write(TEMP_AUDIO_FILE, audio_np, SAMPLE_RATE)
    ui.update_console_title("DECODING")
    
    # Pass ONLY the vocabulary terms as the Whisper hint. The old English framing
    # ("Bilingual engine ... Context: <clipboard>") biased the decoder into writing
    # spoken Arabic as English. A bare term list preserves proper-noun spelling
    # without forcing the output language, so Arabic speech stays Arabic.
    vocab_terms = load_adapted_vocabulary()
    final_initial_prompt = ", ".join(vocab_terms) if vocab_terms else None
    
    # Auto-detect the spoken language in every mode so the engine is genuinely
    # bilingual (Arabic stays Arabic, English stays English). The dedicated
    # "english" hotkey is the one explicit exception: it forces English output.
    whisper_language = "en" if active_mode == "english" else None
    detected_lang = None
    transcribed_text = ""
    try:
        # condition_on_previous_text=False stops the decoder from feeding its own
        # output back in and spiralling into repetition loops (the "الوصفة الوصفة"
        # hallucination). beam_size=5 gives steadier short-clip decoding.
        def _decode(lang):
            segs, inf = model.transcribe(TEMP_AUDIO_FILE, beam_size=5, vad_filter=True,
                                         condition_on_previous_text=False, language=lang,
                                         initial_prompt=final_initial_prompt)
            return "".join(s.text for s in segs).strip(), inf

        transcribed_text, info = _decode(whisper_language)
        detected_lang = info.language

        # This engine is Arabic/English only. If auto-detect wandered off to a third
        # language (Malay/Indonesian/Hebrew… = gibberish), re-decode forcing whichever
        # of ar/en scored higher, so the output is never a language you didn't speak.
        if whisper_language is None and detected_lang not in ("ar", "en"):
            probs = dict(getattr(info, "all_language_probs", None) or [])
            forced = "ar" if probs.get("ar", 0) >= probs.get("en", 0) else "en"
            logging.warning(f"Detected '{detected_lang}' (not ar/en) — re-decoding as '{forced}'.")
            transcribed_text, info = _decode(forced)
            detected_lang = forced
    except Exception as e:
        logging.error(f"Whisper transcription failed: {e}")
        transcribed_text = ""
    logging.info(f"Transcription result (mode={active_mode}, lang={detected_lang}): {transcribed_text!r}")
    
    if os.path.exists(TEMP_AUDIO_FILE): os.remove(TEMP_AUDIO_FILE)

    if transcribed_text:
        print(f"📝 Raw: {transcribed_text}")
        if active_mode == "polish":
            ui.update_console_title("OLLAMA PROCESSING")
            transcribed_text = query_local_ollama(transcribed_text, clipboard_context, personas.STANDARD_SYSTEM_PROMPT)
            print(f"✨ Polished: {ui.C_GOOD}{transcribed_text}{ui.C_RESET}")
            ui.show_toast("✨ Polish Complete", "Cleaned prose injected.", ENABLE_TOASTS)
            ui.play_tone("success_polish", ENABLE_AUDIO_CHIMES)
        elif active_mode == "translate":
            ui.update_console_title("OLLAMA TRANSLATING")
            # Whisper detected the source language → pick the opposite as target.
            # Arabic in → English out; anything else (English) in → Arabic out.
            if detected_lang == "ar":
                direction, translate_prompt = "AR→EN", personas.TRANSLATE_TO_EN_PROMPT
            else:
                direction, translate_prompt = "EN→AR", personas.TRANSLATE_TO_AR_PROMPT
            transcribed_text = query_local_ollama(transcribed_text, None, translate_prompt)
            print(f"🌐 Translated [{direction}]: {ui.C_WARN}{transcribed_text}{ui.C_RESET}")
            ui.show_toast("🌐 Translation Complete", f"{direction} prose injected.", ENABLE_TOASTS)
            ui.play_tone("success_translate", ENABLE_AUDIO_CHIMES)
        else:
            ui.play_tone("success_raw", ENABLE_AUDIO_CHIMES)
            
        execute_smart_injection(transcribed_text)
        log_to_history(transcribed_text, active_mode)
    else:
        logging.info("Empty transcription — nothing injected (silence / VAD dropped all audio).")
        ui.play_tone("empty", ENABLE_AUDIO_CHIMES)
    ui.update_console_title("ONLINE")

# =====================================================================
# CONTROLS & TRIGGERS
# =====================================================================
def trigger_panic_switch():
    global recording, cancel_flag
    # Esc ONLY cancels an in-progress recording now. It used to send Ctrl+Z (undo)
    # on every idle press — but Esc is pressed constantly, so that was silently
    # undoing things in whatever app had focus ("the cursor moves when I press a
    # key"). To undo an injection, use your app's own Ctrl+Z.
    if recording:
        cancel_flag = True
        recording = False
        ui.set_tray_state(False)
        print(f"\n{ui.C_ERR}🛑 Recording cancelled.{ui.C_RESET}")
        ui.play_tone("cancel", ENABLE_AUDIO_CHIMES)

def trigger_hotkey_toggle(mode_selection):
    global recording, active_mode, clipboard_context, cancel_flag
    
    if recording:
        # Any record hotkey STOPS the active capture. We no longer switch modes
        # mid-recording — that silent switch (e.g. tapping F11 while recording a
        # raw F9 clip) was the cause of "it translated when I didn't ask for it".
        # The mode is locked in when the recording starts.
        recording = False
        ui.set_tray_state(False)
        ui.play_tone("stop", ENABLE_AUDIO_CHIMES)
        return

    cancel_flag = False
    try: clipboard_context = re.sub(URL_PATTERN, '', pyperclip.paste())[:500]
    except Exception: clipboard_context = ""

    active_mode = mode_selection; recording = True
    ui.set_tray_state(True)
    print(f"\n{ui.C_ACCENT}🔴 [{active_mode.upper()}] Capturing audio...{ui.C_RESET}")
    ui.play_tone("start", ENABLE_AUDIO_CHIMES)
    threading.Thread(target=core_processing_engine).start()

def execute_inline_line_correction():
    if recording: return
    print(f"\n{ui.C_ACCENT}⚡ Running contextual line refinement...{ui.C_RESET}")
    ui.play_tone("start", ENABLE_AUDIO_CHIMES)
    
    backup_clip = pyperclip.paste()
    keyboard.send('shift+home'); time.sleep(0.05)
    keyboard.send('ctrl+c'); time.sleep(0.05)
    
    target_text = pyperclip.paste().strip()
    if not target_text or target_text == backup_clip:
        ui.play_tone("empty", ENABLE_AUDIO_CHIMES); return
        
    fixed_output = query_local_ollama(target_text, None, personas.LINE_CORRECTION_PROMPT)
    if fixed_output and fixed_output != target_text:
        print(f"✨ Optimized: '{ui.C_GOOD}{fixed_output}{ui.C_RESET}'")
        pyperclip.copy(fixed_output); time.sleep(0.03)
        keyboard.send('ctrl+v'); time.sleep(0.03)
        ui.play_tone("correction", ENABLE_AUDIO_CHIMES)
        log_to_history(fixed_output, "line_fix")
    else:
        keyboard.send('right'); ui.play_tone("stop", ENABLE_AUDIO_CHIMES)
        
    pyperclip.copy(backup_clip)

try:
    # suppress=True consumes the key so it never reaches the focused app. Without it,
    # F11 toggled browser fullscreen, F10 opened menu bars, etc. — keys "leaking"
    # into your apps. Esc stays un-suppressed so it still works normally everywhere.
    keyboard.add_hotkey(HOTKEYS["raw"], lambda: trigger_hotkey_toggle("raw"), suppress=True)
    keyboard.add_hotkey(HOTKEYS["polish"], lambda: trigger_hotkey_toggle("polish"), suppress=True)
    keyboard.add_hotkey(HOTKEYS["translate"], lambda: trigger_hotkey_toggle("translate"), suppress=True)
    keyboard.add_hotkey(HOTKEYS["english"], lambda: trigger_hotkey_toggle("english"), suppress=True)
    keyboard.add_hotkey(HOTKEYS["fix"], execute_inline_line_correction, suppress=True)
    keyboard.add_hotkey(HOTKEYS["maintenance"], execute_memory_maintenance, suppress=True)
    keyboard.add_hotkey(HOTKEYS["panic"], trigger_panic_switch)
    keyboard.wait()
except Exception as e:
    logging.critical(f"Fatal Engine Crash: {traceback.format_exc()}")