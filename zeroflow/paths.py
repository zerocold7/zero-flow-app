"""Where the engine's files live: all in the program folder (the project root)."""
import os

# The program folder — one level above this package. Logos, .env, the vocabulary and
# the history all live there.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOCAB_CACHE_FILE = os.path.join(BASE_DIR, "flow_vocabulary.txt")
HISTORY_FILE = os.path.join(BASE_DIR, "flow_history.md")


def log_dir() -> str:
    """Where the debug and crash logs go: the program folder, unless ZEROFLOW_LOG_DIR
    says otherwise. The test suite points it at a temporary folder, so its deliberate
    crashes never read like real faults in the logs you look at. Read when a log is
    opened, not at import, so setting it any time before then works."""
    return os.getenv("ZEROFLOW_LOG_DIR") or BASE_DIR


def log_path(component: str) -> str:
    return os.path.join(log_dir(), f"{component}_debug.log")
