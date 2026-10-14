"""Every setting the engine reads from .env, in one place.

.env is read from the program folder (not from wherever the engine was started), and
before anything else, so every value below sees it. Restart the engine after editing.
"""
import os

from dotenv import load_dotenv

from zeroflow.paths import BASE_DIR

load_dotenv(os.path.join(BASE_DIR, ".env"))
OLLAMA_HOST_URL   = os.getenv("OLLAMA_HOST_URL", "http://127.0.0.1:11434/api/generate")
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "").strip()  # pin an exact model (e.g. qwen2.5:7b); blank = auto-discover
FALLBACK_LLM      = os.getenv("FALLBACK_LLM", "gemma2:27b")


# How long Ollama keeps the model in memory after a request. Its own default is 5
# minutes, and reloading afterwards made the next Polish wait 3-12 s. "0" unloads at once.
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m").strip()


# The AI model's working memory, in tokens. A model file may ask for far more than a
# dictation needs — gemma4-e4b's asks for 131,072, which held 3.58 GB of graphics
# memory against 2.99 GB at 8,192, with the same speed and answers. 8,192 still fits
# a five-minute dictation and its answer. 0 keeps whatever the model file says.
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", 8192))
ENABLE_AUDIO_CHIMES = os.getenv("ENABLE_AUDIO_CHIMES", "True").lower() in ('true', '1', 't')
ENABLE_TOASTS       = os.getenv("ENABLE_TOAST_NOTIFICATIONS", "True").lower() in ('true', '1', 't')


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


# A recording left running stops by itself after this long, and is transcribed as
# usual. Without a limit a forgotten one grew by ~4 MB a minute.
MAX_RECORDING_SECONDS = float(os.getenv("MAX_RECORDING_SECONDS", 300))
