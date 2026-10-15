"""The rotating debug log and crash logging, one per process.

Each half logs to its own file: "flow_debug.log" and "reader_debug.log". That is
deliberate. Two processes sharing one RotatingFileHandler fight at rollover — on
Windows the rename fails outright while the other process holds the file open, and
the log then grows without bound, which is exactly what the rotation is there to
prevent. Each file rotates independently (~1 MB live + two backups, ~3 MB cap).
"""
import faulthandler
import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler

from zeroflow.paths import log_dir, log_path

_handler = None           # this process's debug log, once init_logging has run
_crash_file = None        # kept open for the life of the process: faulthandler writes to it


def init_logging(component: str) -> logging.Handler:
    """Attach this process's rotating debug log.

    One log per process: the first caller names the file and every later call gets
    that same handler back. The two halves always run as separate processes, so that
    means flow_debug.log and reader_debug.log.
    """
    global _handler
    if _handler is not None:
        return _handler
    _handler = RotatingFileHandler(log_path(component), maxBytes=1_000_000,
                                   backupCount=2, encoding="utf-8")
    _handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(_handler)
    _log_crashes(component)
    return _handler


def _log_crashes(component: str) -> None:
    """Make sure a crash leaves a trace. Uncaught exceptions — on any thread — go to
    the debug log; a native crash (a segfault in a CUDA library, say), which skips
    Python's error handling entirely, is written by faulthandler to
    `<component>_crash.log`. Before this, both left nothing at all."""
    def log_uncaught(exc_type, exc, tb):
        logging.critical("Uncaught exception", exc_info=(exc_type, exc, tb))

    sys.excepthook = log_uncaught
    threading.excepthook = lambda args: logging.critical(
        f"Uncaught exception in thread {args.thread.name if args.thread else '?'}",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    global _crash_file
    try:
        _crash_file = open(os.path.join(log_dir(), f"{component}_crash.log"), "a", encoding="utf-8")
        faulthandler.enable(file=_crash_file)
    except Exception as e:
        logging.warning(f"Native crash logging unavailable: {e}")
