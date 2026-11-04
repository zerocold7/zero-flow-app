"""How heavy each part of the engine is on this PC: load time, memory, graphics memory,
and the time each step takes once loaded. The numbers optimisations are judged by.

    venv\\Scripts\\python.exe tools\\bench\\measure_load.py

Each part runs in a fresh process, one after another, so their memory is not mixed:
  dictation   import, Whisper load, one transcription (cold and warm), the per-
              dictation text work (spoken commands, punctuation, vocabulary)
  ai          the built-in AI: start, one Polish (cold and warm), then unloaded
  reader      the voice on the device READER_DEVICE picks: load, the start-up warm-up
              (as the reader does it), then time to the first sound and real-time
              factor for a paragraph
  reader-cpu  the same, forced onto the processor

Graphics memory is the card's total use before and after loading (nvidia-smi), so
another program changing its use at the same moment would show up in it. Logs go to a
temporary folder, removed afterwards.
"""
import ctypes
import json
import os
import subprocess
import sys
import time
import wave
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from zeroflow.paths import use_temporary_log_dir  # noqa: E402

use_temporary_log_dir("zeroflow-measure-")  # inherited by each part's process
PARAGRAPH = ("The engine reads the highlighted text aloud. It splits the text into short "
             "batches, so the first words start playing while the rest is still being "
             "made. On a graphics card that takes a fraction of a second; on the processor "
             "it takes longer, but playback should still never have to wait.")


class MEMORY(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
            "PagefileUsage", "PeakPagefileUsage")]


def ram_mb(pid=None) -> float:
    """Working set of process `pid` (this one by default), in MB."""
    kernel32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.GetCurrentProcess() if pid is None else kernel32.OpenProcess(0x0410, False, pid)
    info = MEMORY()
    info.cb = ctypes.sizeof(info)
    psapi.GetProcessMemoryInfo(wintypes.HANDLE(handle), ctypes.byref(info), info.cb)
    return info.WorkingSetSize / 2**20


def gpu_mb() -> float | None:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout
        return float(out.split()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def clip(name="en_01_mine.wav"):
    import numpy as np
    with wave.open(os.path.join(ROOT, "tools", "bench", "mine", name)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768


def timed(fn):
    started = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - started


def part_dictation() -> dict:
    gpu0 = gpu_mb()
    _, imported = timed(lambda: __import__("zeroflow.engine"))
    from zeroflow import stt
    from zeroflow.text.macros import format_text, take_commands
    stt.model, loaded = timed(stt.load_whisper_model)
    audio = clip()
    _, cold = timed(lambda: stt.transcribe_audio(audio, "en"))
    _, warm = timed(lambda: stt.transcribe_audio(audio, "en"))
    sentence = "new line please send the report to Tamara comma thanks and send"
    _, text_work = timed(lambda: [format_text(*take_commands(sentence)[:2]) for _ in range(100)])
    gpu1 = gpu_mb()
    return {"import s": imported, "load s": loaded, "clip s": len(audio) / 16000,
            "transcribe cold s": cold, "transcribe warm s": warm,
            "text work per dictation ms": text_work * 10, "runs on": stt.model_runtime,
            "RAM MB": ram_mb(), "GPU MB": None if gpu0 is None else gpu1 - gpu0}


def part_ai() -> dict:
    from zeroflow import personas
    from zeroflow.llm import builtin
    gpu0 = gpu_mb()
    ok, started = timed(builtin.start)
    assert ok, "the built-in AI did not start"
    gpu1 = gpu_mb()
    server_ram = ram_mb(builtin._process.pid) if builtin._process else None
    ask = lambda: builtin.ask("um so the meeting is uh moved to thursday", None,  # noqa: E731
                              personas.STANDARD_SYSTEM_PROMPT, timeout=120)
    _, cold = timed(ask)
    _, warm = timed(ask)
    builtin.unload()
    return {"start s": started, "polish cold s": cold, "polish warm s": warm,
            "runs on": builtin._variant(), "server RAM MB": server_ram,
            "GPU MB": None if gpu0 is None else gpu1 - gpu0}


def part_reader() -> dict:
    gpu0 = gpu_mb()
    _, imported = timed(lambda: __import__("reader.voice_engine"))
    from reader import voice_engine
    pipeline, loaded = timed(voice_engine.get_pipeline)
    voice = voice_engine._voice(voice_engine.current_voice)
    _, warm_up = timed(lambda: list(pipeline("Ready.", voice=voice)))   # as preload() does
    rate = voice_engine.OUTPUT_SAMPLE_RATE
    started = time.perf_counter()
    first = None
    samples = 0
    for batch in voice_engine._iter_batches(PARAGRAPH):
        for _, _, audio in pipeline(batch, voice=voice):
            if audio is not None:
                first = first or time.perf_counter() - started
                samples += len(audio)
    total = time.perf_counter() - started
    gpu1 = gpu_mb()
    return {"import s": imported, "load s": loaded, "warm-up s": warm_up, "first sound s": first,
            "speech s": samples / rate, "made in s": total,
            "real-time factor": (samples / rate) / total,
            "runs on": voice_engine.resolve_device(), "RAM MB": ram_mb(),
            "GPU MB": None if gpu0 is None else gpu1 - gpu0}


PARTS = {"dictation": (part_dictation, {}), "ai": (part_ai, {}),
         "reader": (part_reader, {}), "reader-cpu": (part_reader, {"READER_DEVICE": "cpu"})}


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--part":
        print("RESULT " + json.dumps(PARTS[sys.argv[2]][0]()))
        return
    for name, (_, env) in PARTS.items():
        run = subprocess.run([sys.executable, os.path.abspath(__file__), "--part", name],
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             env={**os.environ, **env}, cwd=ROOT)
        line = next((ln for ln in run.stdout.splitlines() if ln.startswith("RESULT ")), None)
        if line is None:
            print(f"{name}: FAILED\n{run.stderr[-1500:]}")
            continue
        result = json.loads(line[7:])
        print(f"{name}:")
        for key, value in result.items():
            shown = f"{value:.2f}" if isinstance(value, float) else value
            print(f"    {key:<28} {shown}")


if __name__ == "__main__":
    main()
