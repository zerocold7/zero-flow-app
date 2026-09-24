"""
Zero- Flow Engine — shared core.

Everything both halves of the engine need: paths, `.env` configuration, the rotating
debug log, the learned-vocabulary store, and the single client for the local LLM.

    local_flow.py  — speech → text (dictation, translation, line fixes)
    reader/        — text → speech (reads the highlighted selection aloud)

Both import this module, so there is exactly one Ollama client and one vocabulary file
for the whole product. Each half keeps its own debug log (see `init_logging`), because
the two always run as separate processes. See ARCHITECTURE.md.
"""
import os
import re
import logging
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
_log_handlers = {}


def log_path(component):
    return os.path.join(BASE_DIR, f"{component}_debug.log")


def init_logging(component):
    """Attach this process's rotating debug log.

    One log per process: the first caller names the file and every later call gets
    that same handler back. The two halves always run as separate processes, so that
    means flow_debug.log and reader_debug.log.
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
# How long Ollama keeps the model in memory after a request. Its own default is 5
# minutes, and reloading afterwards made the next Polish wait 3-12 s. "0" unloads at once.
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m").strip()

ENABLE_AUDIO_CHIMES = os.getenv("ENABLE_AUDIO_CHIMES", "True").lower() in ('true', '1', 't')
ENABLE_TOASTS       = os.getenv("ENABLE_TOAST_NOTIFICATIONS", "True").lower() in ('true', '1', 't')

LEARN_PATTERN = re.compile(r'\[LEARN:\s*(.*?)\]')
# Chinese, Japanese and Korean script. The engine only ever wants English or Arabic, and
# some models (qwen2.5) slip into Chinese when handed Arabic.
FOREIGN_SCRIPT = re.compile(r'[\u3040-\u30FF\u3400-\u9FFF\uAC00-\uD7AF\uF900-\uFAFF]')

# =====================================================================
# CLIPBOARD
# =====================================================================
# Both halves drive the clipboard: the reader copies the selection, the dictation
# half pastes into the focused app, and each restores what it found. Overlap either
# of those and one clobbers the other mid-flight. Hold this around any sequence that
# writes the clipboard and reads it back:
#
#     with flow_core.clipboard_lock():
#         ...
#
# Backed by a named Windows mutex, so it serialises the two halves whether they are
# threads in one process or two separate processes.
from flow_signals import clipboard_lock            # re-exported: one import for callers

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
                  "options": {"temperature": 0.2},
                  # Reasoning models (gemma4) otherwise write ~800 hidden tokens before
                  # a one-line answer: 5-9 s instead of 0.8 s, same result. Models
                  # without reasoning accept and ignore it.
                  "think": False,
                  "keep_alive": OLLAMA_KEEP_ALIVE},
            timeout=timeout,
        )
        ui.stop_processing_spinner()
        if response.status_code == 200:
            output = response.json().get("response", raw_text).strip()
            return _absorb_learned_word(output, heard=raw_text)
        # Typically a model name Ollama does not have (404). Without this the text
        # just comes back unpolished and nothing anywhere says why.
        logging.warning(f"Ollama returned HTTP {response.status_code}: {response.text[:200]}")
        ui.show_toast("⚠️ LLM Error", f"Ollama returned HTTP {response.status_code}.", ENABLE_TOASTS)
    except Exception as e:
        ui.stop_processing_spinner()
        logging.warning(f"Ollama request failed: {e}")
        ui.show_toast("⚠️ LLM Offline", "Ollama API failed to respond.", ENABLE_TOASTS)
    return raw_text

def warm_up_llm():
    """Load the model into Ollama ahead of the first Polish or Translate, so that one
    is not the 3-12 s reload. Run on a background thread; stays quiet if Ollama is
    not running (the first real request then reports it)."""
    try:
        requests.post(OLLAMA_HOST_URL, json={"model": get_ollama_model(),
                                             "keep_alive": OLLAMA_KEEP_ALIVE}, timeout=120)
        logging.info(f"LLM '{get_ollama_model()}' loaded ahead of first use.")
    except Exception as e:
        logging.info(f"LLM warm-up skipped: {e}")

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

def _squash(text):
    return re.sub(r"[\s\-_.]", "", text.lower())

def _absorb_learned_word(output, heard=None):
    """If the LLM tagged a new term as `[LEARN: word]`, persist it and strip the tag.

    `heard` is what was actually said. A term is only learned if it appears there
    (ignoring case and spacing, so "chroma db" still teaches "ChromaDB"): models also
    "learn" words nobody said — a misheard Arabic word, or a Chinese one — and every
    learned word is fed to Whisper as a hint on each later dictation."""
    match = LEARN_PATTERN.search(output)
    if not match:
        return output
    word = match.group(1).strip()
    if word and (FOREIGN_SCRIPT.search(word)
                 or (heard is not None and _squash(word) not in _squash(heard))):
        logging.info(f"Ignored a learned word that was not in what was said: {word!r}")
    elif word and word not in load_vocabulary():
        with open(VOCAB_CACHE_FILE, "a", encoding="utf-8") as f:
            f.write(f"{word}\n")
        ui.show_toast("🧠 Learned New Word", f"Added '{word}'", ENABLE_TOASTS)
    return LEARN_PATTERN.sub('', output).strip()
