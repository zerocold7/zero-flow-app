"""Phase 7: how long a start takes, source against a PyInstaller build.

    venv\\Scripts\\python tools\\measure_start.py [--reader] <command ...>
    e.g.  tools\\measure_start.py venv\\Scripts\\pythonw.exe zero_flow.py
          tools\\measure_start.py --reader dist\\gpu\\ZeroFlow\\ZeroFlow.exe

It runs against a copy of your settings in a temporary folder, with its own log folder
and the built-in AI not loaded at start. Prints the seconds until Raw dictation can run
("Whisper model active" in flow_debug.log) and on which device.

--reader also keeps the Reader on: it waits for "Kokoro TTS pipeline loaded" in
reader_debug.log, and counts the processes running the command's program, which must
be two (the Engine and its Reader child), never a second Engine. Nothing else may be
running as Zero- Flow.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from zeroflow import paths, signals  # noqa: E402

LIMIT = 180
WHISPER_READY = "Whisper model active"
READER_READY = "Kokoro TTS pipeline loaded"


def first_line(path: str, text: str) -> str | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as f:
        return next((x for x in f if text in x), None)


def processes_named(exe: str) -> int:
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {os.path.basename(exe)}", "/NH"],
                         capture_output=True, text=True).stdout
    return sum(1 for line in out.splitlines() if line.lower().startswith(
        os.path.basename(exe).lower()))


def main(argv):
    reader = "--reader" in argv
    command = [a for a in argv if a != "--reader"]
    command = [os.path.join(ROOT, command[0]), *command[1:]]   # Popen does not search cwd=
    folder = tempfile.mkdtemp(prefix="zeroflow-start-")
    try:
        with open(paths.settings_file(), encoding="utf-8") as f:
            values = json.load(f)
        values.update(READER_ON=reader, AI_LOAD_AT_START=False)
        settings = os.path.join(folder, paths.SETTINGS_NAME)
        with open(settings, "w", encoding="utf-8") as f:
            json.dump(values, f)
        logs = os.path.join(folder, "logs")
        env = dict(os.environ, ZEROFLOW_SETTINGS=settings, ZEROFLOW_LOG_DIR=logs)
        flow_log = os.path.join(logs, "flow_debug.log")
        reader_log = os.path.join(logs, "reader_debug.log")
        start = time.perf_counter()
        child = subprocess.Popen(command, cwd=ROOT, env=env)
        whisper = voice = None
        seen = {}
        while time.perf_counter() - start < LIMIT and child.poll() is None:
            whisper = whisper or first_line(flow_log, WHISPER_READY)
            if whisper and "whisper" not in seen:
                seen["whisper"] = time.perf_counter() - start
            if reader:
                voice = voice or first_line(reader_log, READER_READY)
                if voice and "reader" not in seen:
                    seen["reader"] = time.perf_counter() - start
                    seen["processes"] = processes_named(command[0])
            if whisper and (voice or not reader):
                break
            time.sleep(0.1)
        signals.request_exit()
        try:
            child.wait(timeout=30)
        except subprocess.TimeoutExpired:
            child.kill()
        if "whisper" not in seen or (reader and "reader" not in seen):
            for path in (flow_log, reader_log):
                if os.path.exists(path):
                    print(f"--- {os.path.basename(path)}\n"
                          f"{open(path, encoding='utf-8', errors='replace').read()[-800:]}")
            print(f"NOT READY within {LIMIT} s (exit code {child.returncode}): {seen}")
            return 1
        print(f"dictation ready in {seen['whisper']:.1f} s - {whisper.strip()[-45:]}")
        if reader:
            print(f"reader ready in {seen['reader']:.1f} s - {voice.strip()[-30:]}; "
                  f"processes: {seen['processes']}")
        return 0
    finally:
        time.sleep(1)
        shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
