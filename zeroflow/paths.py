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


def use_temporary_log_dir(prefix: str) -> None:
    """Point the logs at a new temporary folder for this run (the tests and the
    tools/ checks), and remove it when the process ends — unless ZEROFLOW_LOG_DIR is
    set already, which is then kept. Left behind, one folder per run piled up in the
    system's Temp: 826 of them."""
    if os.getenv("ZEROFLOW_LOG_DIR"):
        return
    import atexit
    import tempfile
    folder = tempfile.mkdtemp(prefix=prefix)
    os.environ["ZEROFLOW_LOG_DIR"] = folder
    atexit.register(_remove_log_dir, folder)


def _remove_log_dir(folder: str) -> None:
    """Close the logs first: Windows will not delete a file that is still open."""
    import faulthandler
    import logging
    import shutil
    import sys
    logging.shutdown()
    logs = sys.modules.get("zeroflow.logs")
    if logs is not None and logs._crash_file is not None:
        faulthandler.disable()
        logs._crash_file.close()
    shutil.rmtree(folder, ignore_errors=True)
