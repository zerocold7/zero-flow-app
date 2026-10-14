"""flow_history.md: every dictation, kept to a fixed size."""
import logging
import os
import re
from datetime import datetime

from zeroflow.paths import HISTORY_FILE


# flow_history.md is trimmed back to its newest content once it grows past this.
HISTORY_MAX_BYTES = 500_000


def log_to_history(text: str, mode: str) -> None:
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


def cap_history_file() -> None:
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
