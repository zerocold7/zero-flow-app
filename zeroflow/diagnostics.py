"""Copy diagnostics: what someone helping you needs, and nothing private.

It holds the version, check_hardware's detect(), the settings in effect and the last
LOG_TAIL lines of each Debug log. It never holds an API key, dictated words or the
Dictation history:
- the API key is not a setting, and a key saved in Credential Manager, or anything
  shaped like a well-known key, is hidden wherever it appears;
- an address keeps its server and loses the user part and the query, where keys hide;
- a log line marked as holding dictated words (logs.DICTATED_MARK), or holding the text
  of any history entry, is replaced by a note saying it was left out;
- the history and the learned vocabulary are counted, never shown.
"""
import json
import os
import re
from collections.abc import Callable

import zeroflow
from zeroflow import credentials, history, paths, settings, storage, vocabulary
from zeroflow.logs import DICTATED_MARK

LOG_TAIL = 200
LOGS = ("flow_debug.log", "reader_debug.log")
HIDDEN = "[hidden]"
LEFT_OUT = "(line left out: it held dictated words)"
# History text shorter than this is not looked for in the log: "ok" would match
# half the lines, and words that short say nothing about you.
PRIVATE_MIN_CHARS = 8

# Keys by their shape, saved or not: Anthropic/OpenAI (sk-…), Hugging Face (hf_…),
# Google (AIza…), a Bearer token, and anything written as key=…, token: … and so on.
KEY_SHAPES = [
    re.compile(r"\bsk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{16,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?i)(bearer\s+)\S+"),
    re.compile(r"(?i)\b((?:api[_-]?key|token|secret|password)\s*[=:]\s*)\S+"),
]
# The user part (https://user:secret@host) and the query (?key=…) of an address.
_USER_PART = re.compile(r"(?i)\b(https?://)[^/\s@]+@")
_QUERY = re.compile(r"(?i)\b(https?://[^\s?#]+)[?#]\S*")
_LOG_PREFIX = re.compile(r"^(\d{4}-\d\d-\d\d [\d:,]+ - \w+ - )")


def hide_secrets(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, HIDDEN)
    text = _USER_PART.sub(r"\1", text)
    text = _QUERY.sub(r"\1", text)
    for shape in KEY_SHAPES:
        text = shape.sub(lambda m: (m.group(1) if m.groups() else "") + HIDDEN, text)
    return text


def private_texts(entries: list[history.Entry]) -> list[str]:
    """What a log line must not hold: each history entry, and each of its lines."""
    found = set()
    for entry in entries:
        for piece in [entry.text, *entry.text.splitlines()]:
            piece = piece.strip().lower()
            if len(piece) >= PRIVATE_MIN_CHARS:
                found.add(piece)
    return sorted(found, key=len)


def is_private(line: str, private: list[str]) -> bool:
    if DICTATED_MARK in line:
        return True
    lowered = line.lower()
    return any(piece in lowered for piece in private)


def last_lines(path: str, count: int = LOG_TAIL) -> list[str]:
    """The last `count` lines of a rotating log, reaching into its .1 and .2 backups."""
    lines: list[str] = []
    for name in (path, path + ".1", path + ".2"):
        if len(lines) >= count:
            break
        try:
            with open(name, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines() + lines
        except OSError:
            continue
    return lines[-count:]


def clean_log(lines: list[str], private: list[str], secrets: list[str]) -> list[str]:
    cleaned = []
    for line in lines:
        if is_private(line, private):
            prefix = _LOG_PREFIX.match(line)
            cleaned.append((prefix.group(1) if prefix else "") + LEFT_OUT)
        else:
            cleaned.append(hide_secrets(line, secrets))
    return cleaned


def log_section(text: str, name: str) -> list[str]:
    """The lines under one log's heading in a diagnostics text (for the tests)."""
    lines, inside = [], False
    for line in text.splitlines():
        if line.startswith("=== "):
            inside = line.startswith(f"=== {name} ")
            continue
        if inside and line:
            lines.append(line)
    return lines


def _settings(settings_path: str, store) -> tuple[dict, list[str], str, str | None]:
    """The settings in effect (no key), the problems found, whether a key is saved, and
    the saved key itself (only to hide it)."""
    try:
        raw = storage.load(settings_path)
    except Exception as e:
        return {}, [f"The settings file could not be read: {type(e).__name__}"], "unknown", None
    values, problems = settings.resolve(raw)
    values.pop(storage.KEY_NAME, None)          # a key planted in the file is not shown
    address = credentials.provider_address(str(values.get("AI_PROVIDER", "")).lower(),
                                           str(values.get("AI_URL", "")))
    secret = None
    if address is None:
        saved = "not needed"
    else:
        try:
            secret = store.get(address)
            saved = "yes" if secret else "no"
        except OSError as e:
            saved = f"unknown (error {e.errno})"
    return values, problems, saved, secret


def _default_detect() -> dict:
    from zeroflow.first_run import _hardware
    return _hardware().detect()


def collect(store, settings_path: str | None = None, history_path: str | None = None,
            vocabulary_path: str | None = None, log_dir: str | None = None,
            detect: Callable[[], dict] | None = None) -> str:
    settings_path = settings_path or paths.settings_file()
    history_path = history_path or paths.HISTORY_FILE
    vocabulary_path = vocabulary_path or paths.VOCAB_CACHE_FILE
    log_dir = log_dir or paths.log_dir()

    values, problems, key_saved, secret = _settings(settings_path, store)
    secrets = [secret] if secret else []
    try:
        entries = history.read_entries(history_path)
    except Exception:
        entries = []
    private = private_texts(entries)
    try:
        facts = (detect or _default_detect)()
    except Exception as e:
        facts = {"detect failed": f"{type(e).__name__}: {e}"}
    try:
        words = len(vocabulary.learned_words(vocabulary_path))
    except Exception:
        words = "unknown"

    out = [f"Zero- Flow {zeroflow.__version__}", "",
           "=== This PC ===", json.dumps(facts, indent=2, ensure_ascii=False), "",
           "=== Settings ===",
           json.dumps(values, indent=2, ensure_ascii=False, sort_keys=True, default=str),
           f"API key saved: {key_saved}",
           f"History entries: {len(entries)}", f"Learned words: {words}"]
    if problems:
        out += ["Problems:", *problems]
    for name in LOGS:
        lines = clean_log(last_lines(os.path.join(log_dir, name)), private, secrets)
        out += ["", f"=== {name} (last {len(lines)} lines) ===", *lines]
    return hide_secrets("\n".join(out), secrets) + "\n"


def copy(store, copy: Callable[[str], None], **where) -> str:
    """Collect and put it on the clipboard. Returns the text."""
    text = collect(store, **where)
    copy(text)
    return text
