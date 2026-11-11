"""The Dictation history (history.md in the data folder): every dictation, kept to a fixed size.

The history viewer reads it newest first and deletes from it. Every change to the file
holds HISTORY_LOCK, the same lock a new dictation takes, so a delete never rewrites the
file from an old copy and loses a dictation written meanwhile."""
import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime

from zeroflow import settings
from zeroflow.paths import HISTORY_FILE


# The history file is trimmed back to its newest content once it grows past this.
HISTORY_MAX_BYTES = 500_000

# Held around every write to the history file: a dictation, the trim, the viewer's
# Delete and Clear all.
HISTORY_LOCK = threading.RLock()


def log_to_history(text: str, mode: str) -> None:
    if not text or not settings.KEEP_HISTORY:
        return
    with HISTORY_LOCK:
        try:
            with open(HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] [{mode.upper()}]\n{text}\n\n")
        except Exception as e:
            logging.error(f"History write fail: {e}")
        cap_history_file()


# Where each history entry starts: its "[12:34:56] [MODE]" header at a line start.
HISTORY_ENTRY = re.compile(r"^\[\d\d:\d\d:\d\d\] \[", re.MULTILINE)
_HEADER = re.compile(r"^\[(\d\d:\d\d:\d\d)\] \[([^\]]*)\]\n")


def cap_history_file() -> None:
    """Trim the history file to about half of HISTORY_MAX_BYTES once it passes the cap,
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
        logging.info("History file trimmed (exceeded size cap).")
    except Exception as e:
        logging.error(f"History cap failed: {e}")


# ------------------------------------------------------------------------ the viewer
@dataclass(frozen=True)
class Entry:
    time: str          # "10:15:30": the file keeps no date
    mode: str          # "EN_POLISH"
    text: str


def _read(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def _spans(text: str) -> list[tuple[int, int, Entry]]:
    """Each entry in file order, with where it starts and ends in `text`. What comes
    before the first header (the trim notice) is not an entry."""
    starts = [m.start() for m in HISTORY_ENTRY.finditer(text)]
    spans = []
    for start, end in zip(starts, starts[1:] + [len(text)]):
        block = text[start:end]
        header = _HEADER.match(block)
        if header:
            spans.append((start, end, Entry(header.group(1), header.group(2),
                                            block[header.end():].strip())))
    return spans


def read_entries(path: str = HISTORY_FILE) -> list[Entry]:
    """Every entry, newest first (the file is in the order they were dictated)."""
    return [entry for _, _, entry in reversed(_spans(_read(path)))]


def delete_entry(entry: Entry, path: str = HISTORY_FILE) -> bool:
    """Remove this entry from the file as it is now. The newest copy of it goes when the
    same words were dictated twice at the same second. False if it is no longer there."""
    with HISTORY_LOCK:
        text = _read(path)
        for start, end, found in reversed(_spans(text)):
            if found == entry:
                _write(path, text[:start] + text[end:])
                return True
    return False


def clear(path: str = HISTORY_FILE) -> None:
    """Clear all: the history only. The Debug log is Shift+F2's, not the viewer's."""
    with HISTORY_LOCK:
        if os.path.exists(path):
            _write(path, "")


def _write(path: str, text: str) -> None:
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(temporary, path)
