"""
Zero- Flow Engine — shared core.

Everything both halves of the engine need: paths, `.env` configuration, the rotating
debug log, the learned-vocabulary store, and the single client for the local LLM.

    local_flow.py  — speech → text (dictation, translation, line fixes)
    reader/        — text → speech (reads the highlighted selection aloud)

Both import this module, so there is exactly one Ollama client, one vocabulary file
and one debug log for the whole product. See ARCHITECTURE.md.
"""
import os
import re
import logging
import threading
from logging.handlers import RotatingFileHandler

import requests
from dotenv import load_dotenv

import engine_ui as ui

# =====================================================================
# PATHS
# =====================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VOCAB_CACHE_FILE = os.path.join(BASE_DIR, "flow_vocabulary.txt")
TEMP_AUDIO_FILE = os.path.join(BASE_DIR, "flow_capture.wav")
HISTORY_FILE = os.path.join(BASE_DIR, "flow_history.md")

# =====================================================================
# LOGGING
# =====================================================================
# Each half logs to its own file: "flow_debug.log" and "reader_debug.log". That is
# deliberate. Two processes sharing one RotatingFileHandler fight at rollover — on
# Windows the rename fails outright while the other process holds the file open, and
# the log then grows without bound, which is exactly what the rotation is there to
# prevent. Each file rotates independently (~1 MB live + two backups, ~3 MB cap).
LOG_COMPONENTS = ("flow", "reader")
_log_handlers = {}


def log_path(component):
    return os.path.join(BASE_DIR, f"{component}_debug.log")


def init_logging(component):
    """Attach this process's rotating debug log.

    One log per process: the first caller names the file and every later call gets
    that same handler back. Split across two processes that means flow_debug.log and
    reader_debug.log; in the merged single-process engine both halves land in
    flow_debug.log, which is the whole point of merging them.
    """
    if _log_handlers:
        return next(iter(_log_handlers.values()))
    handler = RotatingFileHandler(log_path(component), maxBytes=1_000_000,
                                  backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    _log_handlers[component] = handler
    return handler


load_dotenv()

# =====================================================================
# CONFIGURATION (shared by both halves)
# =====================================================================
OLLAMA_HOST_URL   = os.getenv("OLLAMA_HOST_URL", "http://127.0.0.1:11434/api/generate")
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "").strip()  # pin an exact model (e.g. qwen2.5:7b); blank = auto-discover
FALLBACK_LLM      = os.getenv("FALLBACK_LLM", "gemma2:27b")

ENABLE_AUDIO_CHIMES = os.getenv("ENABLE_AUDIO_CHIMES", "True").lower() in ('true', '1', 't')
ENABLE_TOASTS       = os.getenv("ENABLE_TOAST_NOTIFICATIONS", "True").lower() in ('true', '1', 't')

LEARN_PATTERN = re.compile(r'\[LEARN:\s*(.*?)\]')

# =====================================================================
# CLIPBOARD
# =====================================================================
# Both halves drive the clipboard: the reader copies the selection, the dictation
# half pastes into the focused app, and each restores what it found. Overlap either
# of those and one clobbers the other mid-flight. Hold this around any sequence that
# writes the clipboard and reads it back.
#
# It only serialises callers inside one process, so it does real work in the merged
# engine (zero_flow.py) and is a harmless no-op when the halves run split.
CLIPBOARD_LOCK = threading.RLock()

# =====================================================================
# LOCAL LLM
# =====================================================================
_ollama_model = None      # resolved once, on first use

def discover_ollama_model():
    """Choose the LLM to use, in priority order:
      1. OLLAMA_MODEL_NAME from .env, if set — pins an exact model (e.g. qwen2.5:7b).
      2. Otherwise the first model Ollama is currently serving.
      3. Otherwise FALLBACK_LLM (used when Ollama is unreachable).
    """
    if OLLAMA_MODEL_NAME:
        return OLLAMA_MODEL_NAME
    try:
        tags_url = OLLAMA_HOST_URL.replace("/api/generate", "/api/tags")
        response = requests.get(tags_url, timeout=2)
        if response.status_code == 200 and response.json().get("models"):
            return response.json()["models"][0]["name"]
    except Exception:
        pass
    return FALLBACK_LLM

def get_ollama_model():
    """The active LLM name, discovered lazily on first use and cached afterwards.
    Lazy so the reader does not pay for discovery unless it actually cleans text."""
    global _ollama_model
    if _ollama_model is None:
        _ollama_model = discover_ollama_model()
        logging.info(f"LLM bound to '{_ollama_model}'.")
    return _ollama_model

def query_ollama(raw_text, context_text, instruction, timeout=15.0):
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
            json={"model": get_ollama_model(), "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.2}},
            timeout=timeout,
        )
        ui.stop_processing_spinner()
        if response.status_code == 200:
            output = response.json().get("response", raw_text).strip()
            return _absorb_learned_word(output)
    except Exception:
        ui.stop_processing_spinner()
        ui.show_toast("⚠️ LLM Offline", "Ollama API failed to respond.", ENABLE_TOASTS)
    return raw_text

# =====================================================================
# VOCABULARY
# =====================================================================
def load_vocabulary():
    """Base vocabulary plus any words the LLM has learned over time."""
    import personas                              # imported here to keep this module import-light
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
