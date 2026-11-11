"""Measure an Engine restart: from the old Engine ending until the new one can take a
dictation (Phase 5b, step 2).

    venv\\Scripts\\python tools\\measure_restart.py [cycles]

It starts the real Engine, asks it to exit the way the tray's "Exit Engine" does
(zeroflow.signals.request_exit), and starts the next one. Times are seconds from the
moment the old process is gone:
  speech - "Whisper model active" in flow_debug.log: Raw dictation can run
  ai     - the built-in AI answers on its port: Polish and Translate can run
Nothing else may be running as Zero- Flow.
"""
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from zeroflow import paths  # noqa: E402

LOG = os.path.join(paths.ready_log_dir(), "flow_debug.log")
AI_HEALTH = "http://127.0.0.1:39281/health"
LIMIT = 90
SETTLE = 10          # let the Engine finish starting (its exit watcher must exist) before asking it to exit


def log_size() -> int:
    return os.path.getsize(LOG) if os.path.exists(LOG) else 0


def log_has(offset: int, text: str) -> bool:
    with open(LOG, "rb") as f:
        f.seek(offset)
        return text.encode() in f.read()


def ai_up() -> bool:
    try:
        with urllib.request.urlopen(AI_HEALTH, timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def ask_exit() -> None:
    """Like the tray does, from a process that then ends: the exit event stays signalled
    while any process holds it open, and the next Engine would see it and quit at once."""
    subprocess.run([sys.executable, "-c", "from zeroflow import signals; signals.request_exit()"],
                   cwd=ROOT, check=True)


def start() -> subprocess.Popen:
    python = os.path.join(ROOT, "venv", "Scripts", "python.exe")
    return subprocess.Popen([python, "zero_flow.py"], cwd=ROOT, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW)


def wait_ready(offset: int, since: float, proc) -> dict:
    marks = {}
    while time.monotonic() - since < LIMIT and "speech" not in marks:
        if proc.poll() is not None:
            marks["died"] = proc.returncode
            break
        if "speech" not in marks and log_has(offset, "Whisper model active"):
            marks["speech"] = time.monotonic() - since
        time.sleep(0.1)
    return marks


def main(cycles: int) -> None:
    if ai_up():
        sys.exit("Something already answers on the built-in AI port; stop it first.")
    print("Cold start (not timed) ...")
    engine = start()
    first = wait_ready(log_size(), time.monotonic(), engine)
    print(f"  cold start: {first}")
    rows = []
    for i in range(cycles):
        time.sleep(SETTLE)
        ask_exit()
        engine.wait(timeout=30)
        gone = time.monotonic()
        offset = log_size()
        engine = start()
        marks = wait_ready(offset, gone, engine)
        rows.append(marks)
        print(f"  restart {i + 1}: " + ", ".join(f"{k} {v:.1f} s" if k != "died" else f"died {v}"
                                                  for k, v in marks.items()))
    time.sleep(SETTLE)
    ask_exit()
    engine.wait(timeout=30)
    for key in ("speech",):
        values = [r[key] for r in rows if key in r]
        if values:
            print(f"{key}: min {min(values):.1f}  max {max(values):.1f}  of {len(values)} restarts")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
