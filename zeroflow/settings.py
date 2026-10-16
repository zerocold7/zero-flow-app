"""Every setting the engine reads from .env, in one place, each one checked.

.env is read from the program folder (not from wherever the engine was started), and
before anything else, so every value below sees it. Restart the engine after editing.

A value that is not what its setting needs ("five" seconds, "gpu" for a device that
takes auto or cpu) does not stop the engine: the default is used instead, and the
mistake is kept in `problems`, which the engine reports by name when it starts.
"""
import ipaddress
import os
from urllib.parse import urlparse

from dotenv import load_dotenv

from zeroflow.paths import BASE_DIR

load_dotenv(os.path.join(BASE_DIR, ".env"))

problems = []                 # one sentence per bad value; reported at start-up

_YES = ("true", "1", "t", "yes", "y", "on")
_NO = ("false", "0", "f", "no", "n", "off")


def _raw(name: str) -> str | None:
    value = os.getenv(name)
    return value.strip() if value is not None and value.strip() else None


def _bad(name: str, raw: str, wanted: str, default):
    problems.append(f'{name}="{raw}" in .env is not {wanted} — using {default}.')
    return default


def text(name: str, default: str) -> str:
    return _raw(name) or default


def switch(name: str, default: bool) -> bool:
    """A yes/no setting: true/false, yes/no, on/off or 1/0, in any case."""
    raw = _raw(name)
    if raw is None:
        return default
    if raw.lower() in _YES:
        return True
    if raw.lower() in _NO:
        return False
    return _bad(name, raw, "true or false", default)


def number(name: str, default: float, minimum: float | None = None) -> float:
    raw = _raw(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return _bad(name, raw, "a number", default)
    if minimum is not None and value < minimum:
        return _bad(name, raw, f"{minimum} or more", default)
    return value


def whole_number(name: str, default: int, minimum: int | None = None,
                 maximum: int | None = None) -> int:
    raw = _raw(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return _bad(name, raw, "a whole number", default)
    if minimum is not None and value < minimum:
        return _bad(name, raw, f"{minimum} or more", default)
    if maximum is not None and value > maximum:
        return _bad(name, raw, f"{maximum} or less", default)
    return value


def choice(name: str, default: str, allowed: tuple[str, ...]) -> str:
    raw = _raw(name)
    if raw is None:
        return default
    if raw.lower() in allowed:
        return raw.lower()
    return _bad(name, raw, " or ".join(allowed), default)


# ---------------------------------------------------------------- the AI model
# Load the AI while Whisper loads, so the first Polish is instant. False leaves it out
# of memory until the first Polish or Translate needs it (that one waits ~4 s).
AI_LOAD_AT_START = switch("AI_LOAD_AT_START", True)
# Which provider runs it (zeroflow/llm): "builtin" (llama-server, run by the engine), "ollama",
# "openai" for any server speaking the OpenAI chat format — then AI_URL, AI_MODEL and, for a
# cloud service, AI_API_KEY — or "claude" (Anthropic, with AI_API_KEY and optionally AI_MODEL).
AI_PROVIDER = text("AI_PROVIDER", "builtin").lower()
AI_URL = text("AI_URL", "http://127.0.0.1:8080/v1/chat/completions")
AI_MODEL = text("AI_MODEL", "")
AI_API_KEY = text("AI_API_KEY", "")


def key_sent_in_the_clear(url: str, api_key: str) -> bool:
    """True if `api_key` would go to another computer over plain http, where anyone on
    the way can read it. This PC's own servers (127.0.0.1, localhost) are fine."""
    address = urlparse(url)
    return bool(api_key) and address.scheme == "http" and not _this_pc(address.hostname)


def _this_pc(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback      # 127.x.x.x, ::1
    except ValueError:
        return False                                     # a name, or no host at all


if AI_PROVIDER == "openai" and key_sent_in_the_clear(AI_URL, AI_API_KEY):
    problems.append(f'AI_URL="{AI_URL}" is plain http, so AI_API_KEY is sent unencrypted — '
                    f'use an https:// address.')

# The built-in AI's llama.cpp build: "auto" picks it from the graphics card (NVIDIA →
# cuda, AMD/Intel card → vulkan, otherwise cpu).
LLAMA_VARIANT = choice("LLAMA_VARIANT", "auto", ("auto", "cuda", "vulkan", "cpu"))
# The built-in AI's model (Google's Gemma 4 E4B, Apache 2.0), its working memory in
# tokens, and the local port its server listens on (this PC only).
AI_BUILTIN_REPO = text("AI_BUILTIN_REPO", "google/gemma-4-E4B-it-qat-q4_0-gguf")
AI_BUILTIN_FILE = text("AI_BUILTIN_FILE", "gemma-4-E4B_q4_0-it.gguf")
AI_NUM_CTX = whole_number("AI_NUM_CTX", 8192, minimum=512)
AI_BUILTIN_PORT = whole_number("AI_BUILTIN_PORT", 39281, minimum=1024, maximum=65535)
OLLAMA_HOST_URL = text("OLLAMA_HOST_URL", "http://127.0.0.1:11434/api/generate")
# Pin an exact model (e.g. qwen2.5:7b); blank = the first model Ollama has installed.
OLLAMA_MODEL_NAME = text("OLLAMA_MODEL_NAME", "")
FALLBACK_LLM = text("FALLBACK_LLM", "gemma2:27b")
# How long Ollama keeps the model in memory after a request. Its own default is 5
# minutes, and reloading afterwards made the next Polish wait 3-12 s. "0" unloads at once.
OLLAMA_KEEP_ALIVE = text("OLLAMA_KEEP_ALIVE", "30m")
# The AI model's working memory, in tokens. A model file may ask for far more than a
# dictation needs — gemma4-e4b's asks for 131,072, which held 3.58 GB of graphics
# memory against 2.99 GB at 8,192, with the same speed and answers. 8,192 still fits
# a five-minute dictation and its answer. 0 keeps whatever the model file says.
OLLAMA_NUM_CTX = whole_number("OLLAMA_NUM_CTX", 8192, minimum=0)

# ---------------------------------------------------------------- sound and notices
ENABLE_AUDIO_CHIMES = switch("ENABLE_AUDIO_CHIMES", True)
ENABLE_TOASTS = switch("ENABLE_TOAST_NOTIFICATIONS", True)

# ---------------------------------------------------------------- speech to text
WHISPER_MODEL_NAME = text("WHISPER_MODEL_NAME", "large-v3")
# "auto" tries the NVIDIA GPU and falls back to the CPU; "cpu" skips the GPU attempt
# (no NVIDIA card, or to leave the card's memory to the local LLM).
WHISPER_DEVICE = choice("WHISPER_DEVICE", "auto", ("auto", "cpu"))
# GPU precision. "int8_float16" halves the speech model's graphics memory — large-v3
# measured 3.9 GB -> 2.0 GB on an RTX 4070, 0.9 s -> 1.1 s per 14 s clip. The CPU
# fallback always uses int8, the only precision that is fast there.
WHISPER_COMPUTE_TYPE = text("WHISPER_COMPUTE_TYPE", "float16").lower()
# A recording left running stops by itself after this long, and is transcribed as
# usual. Without a limit a forgotten one grew by ~4 MB a minute.
MAX_RECORDING_SECONDS = number("MAX_RECORDING_SECONDS", 300, minimum=1)

# ---------------------------------------------------------------- keys
# Each action's .env name and default key.
_HOTKEY_SETTINGS = {
    "en_raw":      ("HOTKEY_EN_RAW", "f5"),
    "en_polish":   ("HOTKEY_EN_POLISH", "f6"),
    "ar_raw":      ("HOTKEY_AR_RAW", "f7"),
    "ar_polish":   ("HOTKEY_AR_POLISH", "f8"),
    "en2ar":       ("HOTKEY_EN2AR", "f9"),
    "ar2en":       ("HOTKEY_AR2EN", "f10"),
    "fix":         ("HOTKEY_FIX", "shift+f3"),
    "maintenance": ("HOTKEY_MAINTENANCE", "shift+f1"),
    "purge":       ("HOTKEY_PURGE", "shift+f2"),
    # Shared with the reader on purpose: one key cancels a recording and silences it.
    "panic":       ("HOTKEY_PANIC", "esc"),
}
HOTKEYS = {action: text(name, default) for action, (name, default) in _HOTKEY_SETTINGS.items()}
# The reader's key: read the highlighted text aloud.
HOTKEY_READ = text("HOTKEY_READ", "f4")


def report_clashing_keys(keys: dict[str, str]) -> None:
    """`keys` maps .env names to keys. Two actions on one key both run on every
    press — F4 set as a record key would dictate and read aloud at once — so each
    clash is reported by name. ("Ctrl+Alt+R" and "alt + ctrl + r" are the same key.)"""
    first = {}
    for name, key in keys.items():
        chord = "+".join(sorted(part.strip() for part in key.lower().split("+")))
        other = first.setdefault(chord, name)
        if other != name:
            problems.append(f'{other} and {name} in .env are both "{key}" — '
                            f'that key does both. Give each its own key.')


report_clashing_keys({name: HOTKEYS[action] for action, (name, _) in _HOTKEY_SETTINGS.items()}
                     | {"HOTKEY_READ": HOTKEY_READ})

# ---------------------------------------------------------------- the reader
READER_VOICE = text("READER_VOICE", "af_heart")
READER_DEVICE = choice("READER_DEVICE", "auto", ("auto", "cpu", "cuda"))
# Off by default: the regex clean is instant, the LLM pass costs a few seconds.
READER_SMART_MODE = switch("READER_SMART_MODE", False)
# Above this length the LLM pass is skipped: a local model needs several seconds per
# thousand characters, which is longer than the wait for speech to simply start.
READER_SMART_MAX_CHARS = whole_number("READER_SMART_MAX_CHARS", 1000, minimum=0)
# The reader is interactive, so it waits less patiently than the dictation engine.
READER_LLM_TIMEOUT = number("READER_LLM_TIMEOUT", 10.0, minimum=1)
READER_FIRST_BATCH_CHARS = whole_number("READER_FIRST_BATCH_CHARS", 120, minimum=20)
READER_BATCH_CHARS = whole_number("READER_BATCH_CHARS", 300, minimum=20)
