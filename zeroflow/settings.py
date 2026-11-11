"""Every setting the engine uses, in one place, each one checked.

They come from one file, %APPDATA%\\ZeroFlow\\settings.json (ADR 0002; a developer
points ZEROFLOW_SETTINGS at another). On the first start there is no such file: the
values are read from the old .env in the program folder, and at the end of this module
the migration (zeroflow.storage) writes them into the new file. .env is never read again.
Restart the engine after editing the file.

A value that is not what its setting needs ("five" seconds, "gpu" for a device that
takes auto or cpu) does not stop the engine: the default is used instead, and the
mistake is kept in `problems`, which the engine reports by name when it starts.
"""
import ipaddress
import os
import sys
from urllib.parse import urlparse

from zeroflow import credentials, paths, storage
from zeroflow.paths import BASE_DIR

problems = []                 # one sentence per bad value; reported at start-up

# Every setting, filled in as each one is read below: name → (checker, default, limits).
# The migration re-runs the same checks on .env with `resolve`.
SPEC = {}
_recording = True

SETTINGS_FILE = paths.settings_file()
_first_start = not os.path.exists(SETTINGS_FILE)
if _first_start:
    _VALUES, _where = storage.read_env(os.path.join(BASE_DIR, ".env")), ".env"
else:
    _where = paths.SETTINGS_NAME
    try:
        _VALUES = storage.load(SETTINGS_FILE)
    except (OSError, ValueError) as e:
        _VALUES = {}
        problems.append(f"{SETTINGS_FILE} could not be read ({e}) — every setting is at its "
                        f"default this time. The file is left as it is.")

# The Python the engine is tested on; also in check_hardware.py (a test keeps them equal).
TESTED_PYTHON = "3.12"


def python_notice(version: tuple[int, int]) -> str | None:
    """A start-up notice when the engine runs on a Python it is not tested on."""
    running = f"{version[0]}.{version[1]}"
    if running == TESTED_PYTHON:
        return None
    return (f"This is Python {running}; the engine is tested on Python {TESTED_PYTHON}. "
            f"If something fails, reinstall with {TESTED_PYTHON} (docs/INSTALL.md step 1).")


if notice := python_notice(sys.version_info[:2]):
    problems.append(notice)

_YES = ("true", "1", "t", "yes", "y", "on")
_NO = ("false", "0", "f", "no", "n", "off")


def _note(name: str, checker, default, **limits) -> None:
    if _recording:
        SPEC.setdefault(name, (checker, default, limits))


def _raw(name: str) -> str | None:
    """The setting as text ("true", "300"), whether the file holds text, a number or a
    yes/no; None when it is missing or blank."""
    value = _VALUES.get(name)
    if value is None:
        return None
    if isinstance(value, bool):
        value = "true" if value else "false"
    value = str(value).strip()
    return value or None


def _bad(name: str, raw: str, wanted: str, default):
    problems.append(f'{name}="{raw}" in {_where} is not {wanted} — using {default}.')
    return default


def resolve(raw: dict) -> tuple[dict, list[str]]:
    """Every setting's value from `raw` (NAME → text, as in .env), with the same checks
    and defaults as at start-up, and the problems found. A name that is no setting is
    reported and left out."""
    global _VALUES, _where, problems
    kept = _VALUES, _where, problems
    _VALUES, _where, problems = raw, ".env", []
    try:
        values = {name: checker(name, default, **limits)
                  for name, (checker, default, limits) in SPEC.items()}
        found = problems + [f"{name} in .env is not a setting Zero- Flow knows — left out."
                            for name in raw if name not in SPEC and name not in RETIRED]
    finally:
        _VALUES, _where, problems = kept
    return values, found


def text(name: str, default: str) -> str:
    _note(name, text, default)
    return _raw(name) or default


def switch(name: str, default: bool) -> bool:
    """A yes/no setting: true/false, yes/no, on/off or 1/0, in any case."""
    _note(name, switch, default)
    raw = _raw(name)
    if raw is None:
        return default
    if raw.lower() in _YES:
        return True
    if raw.lower() in _NO:
        return False
    return _bad(name, raw, "true or false", default)


def number(name: str, default: float, minimum: float | None = None) -> float:
    _note(name, number, default, minimum=minimum)
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
    _note(name, whole_number, default, minimum=minimum, maximum=maximum)
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


def hotkey(name: str, default: str) -> str:
    """A key or chord ("f5", "shift+f3", "ctrl+alt+r"). A key the keyboard library does
    not know ("f55") used to stop the engine at start-up when it was bound."""
    _note(name, hotkey, default)
    raw = _raw(name)
    if raw is None:
        return default
    import keyboard
    try:
        keyboard.parse_hotkey(raw)
    except ValueError:
        return _bad(name, raw, "a key the keyboard knows", default)
    return raw


def choice(name: str, default: str, allowed: tuple[str, ...]) -> str:
    _note(name, choice, default, allowed=allowed)
    raw = _raw(name)
    if raw is None:
        return default
    if raw.lower() in allowed:
        return raw.lower()
    return _bad(name, raw, " or ".join(allowed), default)


# ---------------------------------------------------------------- the models folder
# Where the speech, voice and AI models are downloaded and kept. Set here, before
# anything imports huggingface_hub, which reads HF_HOME once, at import.
MODELS_DIR = text("MODELS_DIR", storage.default_models_dir(os.environ))
storage.apply_models_dir({"MODELS_DIR": MODELS_DIR}, os.environ)

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
# Read from .env only on the first start; from then on, from Credential Manager under the
# provider's address (zeroflow.credentials). Never kept in the settings file.
AI_API_KEY = text("AI_API_KEY", "")
if not AI_API_KEY and (_address := credentials.provider_address(AI_PROVIDER, AI_URL)):
    try:
        AI_API_KEY = credentials.WindowsStore().get(_address) or ""
    except OSError as e:
        problems.append(f"The API key for {_address} could not be read: {e}.")


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

def clipboard_context_sent(setting: str, provider: str, ai_url: str, ollama_url: str) -> bool:
    """Whether Polish hands the AI the clipboard as context. "auto": only an AI on this
    PC gets it — the clipboard often holds a password just copied, and a cloud AI would
    send it to that company with every Polish."""
    if setting != "auto":
        return setting == "on"
    if provider == "builtin":
        return True
    if provider == "ollama":
        return _this_pc(urlparse(ollama_url).hostname)
    if provider == "openai":
        return _this_pc(urlparse(ai_url).hostname)
    return False                                 # claude, or a provider not known here


# The built-in AI's llama.cpp build: "auto" picks it from the graphics card (NVIDIA →
# cuda, AMD/Intel card → vulkan, otherwise cpu).
LLAMA_VARIANT = choice("LLAMA_VARIANT", "auto", ("auto", "cuda", "vulkan", "cpu"))
# The built-in AI's model (Google's Gemma 4 E4B, Apache 2.0).
AI_BUILTIN_REPO = text("AI_BUILTIN_REPO", "google/gemma-4-E4B-it-qat-q4_0-gguf")
AI_BUILTIN_FILE = text("AI_BUILTIN_FILE", "gemma-4-E4B_q4_0-it.gguf")
OLLAMA_HOST_URL = text("OLLAMA_HOST_URL", "http://127.0.0.1:11434/api/generate")
# Pin an exact model (e.g. qwen2.5:7b); blank = the first model Ollama has installed.
OLLAMA_MODEL_NAME = text("OLLAMA_MODEL_NAME", "")
# How long Ollama keeps the model in memory after a request. Its own default is 5
# minutes, and reloading afterwards made the next Polish wait 3-12 s. "0" unloads at once.
OLLAMA_KEEP_ALIVE = text("OLLAMA_KEEP_ALIVE", "30m")
# Polish's clipboard context: "auto" (only to an AI on this PC), "on" or "off".
# (decided for the provider in use: zeroflow.llm.SEND_CLIPBOARD_CONTEXT)
POLISH_CLIPBOARD_CONTEXT = choice("POLISH_CLIPBOARD_CONTEXT", "auto", ("auto", "on", "off"))

# ---------------------------------------------------------------- the debug log
# flow_debug.log records each dictation's size, not its words: a dictated password
# would otherwise sit in the log. True writes the words too, for debugging.
LOG_DICTATION_TEXT = switch("LOG_DICTATION_TEXT", False)

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
}
HOTKEYS = {action: hotkey(name, default) for action, (name, default) in _HOTKEY_SETTINGS.items()}
# Fixed, not a setting: Esc always cancels a recording and silences the reader (one key
# for both, on purpose). A setting for it could only make it clash with another key.
CANCEL_KEY = "esc"
HOTKEYS["panic"] = CANCEL_KEY
# The reader's key: read the highlighted text aloud.
HOTKEY_READ = hotkey("HOTKEY_READ", "f4")


def report_clashing_keys(keys: dict[str, str]) -> None:
    """`keys` maps .env names to keys. Two actions on one key both run on every
    press — F4 set as a record key would dictate and read aloud at once — so each
    clash is reported by name. ("Ctrl+Alt+R" and "alt + ctrl + r" are the same key.)"""
    first = {}
    for name, key in keys.items():
        chord = "+".join(sorted(part.strip() for part in key.lower().split("+")))
        other = first.setdefault(chord, name)
        if other != name:
            problems.append(f'{other} and {name} in {_where} are both "{key}" — '
                            f'that key does both. Give each its own key.')


report_clashing_keys({"Esc (cancel, fixed)": CANCEL_KEY}
                     | {name: HOTKEYS[action] for action, (name, _) in _HOTKEY_SETTINGS.items()}
                     | {"HOTKEY_READ": HOTKEY_READ})

# ---------------------------------------------------------------- the reader
READER_VOICE = text("READER_VOICE", "af_heart")
READER_DEVICE = choice("READER_DEVICE", "auto", ("auto", "cpu", "cuda"))
# Off by default: the regex clean is instant, the LLM pass costs a few seconds.
READER_SMART_MODE = switch("READER_SMART_MODE", False)

# ---------------------------------------------------------------- retired settings
# Settings that became constants in the code that uses them (docs/settings-table.md),
# or were removed. An old .env that still names one migrates without a complaint.
RETIRED = ("HOTKEY_PANIC", "AI_NUM_CTX", "OLLAMA_NUM_CTX", "AI_BUILTIN_PORT", "FALLBACK_LLM",
           "READER_SMART_MAX_CHARS", "READER_LLM_TIMEOUT", "READER_FIRST_BATCH_CHARS",
           "READER_BATCH_CHARS")

# ---------------------------------------------------------------- the first start
_recording = False


def _first_start_migration() -> None:
    """Move .env, the vocabulary and the history into the data folder (zeroflow.storage).
    If that fails the engine does not start: running on, it would write new words and
    dictations where the next start's migration overwrites them."""
    try:
        moved = storage.migrate(BASE_DIR, paths.data_dir(), credentials.WindowsStore(),
                                os.environ, SETTINGS_FILE)
    except Exception as e:
        raise RuntimeError(f"Zero- Flow could not set up {paths.data_dir()}: {e}. "
                           f"Your old files are unchanged; fix this and start again.") from e
    problems.extend(p for p in moved.problems if p not in problems)
    if moved.key_left_in_env:
        problems.append(f"Your API key is now kept in Windows Credential Manager, but the "
                        f"old .env in {BASE_DIR} still holds it. Delete the AI_API_KEY line there.")


if _first_start:
    _first_start_migration()
