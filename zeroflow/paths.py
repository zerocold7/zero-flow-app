"""Where the engine's files live.

The program folder holds the code, the logos and the AI runtime. Your own files live
apart from it (ADR 0002): the settings file, the Learned vocabulary and the Dictation
history in %APPDATA%\\ZeroFlow, the logs in %LOCALAPPDATA%\\ZeroFlow\\logs. A developer
points ZEROFLOW_SETTINGS at another settings file; its folder then holds the rest.
"""
import os

# The program folder — one level above this package.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_NAME = "settings.json"
VOCABULARY_NAME = "vocabulary.txt"
HISTORY_NAME = "history.md"


def _home(variable: str) -> str:
    return os.environ.get(variable) or os.path.expanduser("~")


def settings_file() -> str:
    return os.getenv("ZEROFLOW_SETTINGS") or os.path.join(_home("APPDATA"), "ZeroFlow", SETTINGS_NAME)


def data_dir() -> str:
    """The settings file's folder: it also holds the vocabulary and the history."""
    return os.path.dirname(settings_file())


VOCAB_CACHE_FILE = os.path.join(data_dir(), VOCABULARY_NAME)
HISTORY_FILE = os.path.join(data_dir(), HISTORY_NAME)


def log_dir() -> str:
    """Where the debug and crash logs go: %LOCALAPPDATA%\\ZeroFlow\\logs, unless
    ZEROFLOW_LOG_DIR says otherwise. The test suite points it at a temporary folder, so
    its deliberate crashes never read like real faults in the logs you look at. Read
    when a log is opened, not at import, so setting it any time before then works."""
    return os.getenv("ZEROFLOW_LOG_DIR") or os.path.join(_home("LOCALAPPDATA"), "ZeroFlow", "logs")


def ready_log_dir() -> str:
    """log_dir(), created if it is not there yet (it is not, on a first start)."""
    folder = log_dir()
    os.makedirs(folder, exist_ok=True)
    return folder


def log_path(component: str) -> str:
    return os.path.join(ready_log_dir(), f"{component}_debug.log")


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
