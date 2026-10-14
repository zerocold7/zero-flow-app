"""Record your own voice for the speech benchmark (tools/bench/mine/, git-ignored).

    venv\\Scripts\\python.exe tools\\bench\\record_mine.py
    venv\\Scripts\\python.exe tools\\bench\\bench_stt.py --clips mine --label mine-off --no-filter
    venv\\Scripts\\python.exe tools\\bench\\bench_stt.py --clips mine --label mine-on
    venv\\Scripts\\python.exe tools\\bench\\bench_stt.py --compare mine-off mine-on

Synthetic voices cannot reproduce what makes Whisper invent "Thank you." at the end of
a dictation — your room, your microphone, a breath after the last word. This records
the real thing: it shows a sentence, you read it and then stay as you naturally would
for a few seconds before pressing Enter, exactly like stopping a dictation late. Two
recordings have no words at all.

The recordings never leave this PC and are not part of the project (git-ignored).
Delete tools/bench/mine/ whenever you like.
"""
import json
import os
import sys
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_clips import ARABIC, ENGLISH  # noqa: E402

RATE = 16_000
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mine")
PROMPTS = (
    [("en", text) for _, text in ENGLISH[:8]]
    + [("ar", text) for text in ARABIC[:8]]
    + [("en", ""), ("ar", "")]
)


def record():
    chunks = []
    stop = threading.Event()

    def take(indata, frames, time_info, status):
        if not stop.is_set():
            chunks.append(indata.copy())

    with sd.InputStream(samplerate=RATE, channels=1, dtype="float32", callback=take):
        input()
        stop.set()
    return np.concatenate(chunks)[:, 0] if chunks else np.zeros(0, np.float32)


def main():
    os.makedirs(OUT, exist_ok=True)
    print(__doc__.split("\n\n")[1])
    print("\nFor each one: press Enter to start, read the sentence in your normal voice, then")
    print("stay as you normally would for 2-4 seconds (breathe, move, type if you usually do)")
    print("and press Enter to stop. Type s then Enter to skip one, q then Enter to quit.\n")
    index = []
    for number, (lang, text) in enumerate(PROMPTS, 1):
        what = text if text else "(say nothing — just breathe for about 4 seconds)"
        print(f"[{number}/{len(PROMPTS)}] {'Arabic' if lang == 'ar' else 'English'}:  {what}")
        answer = input("    Enter to start > ").strip().lower()
        if answer == "q":
            break
        if answer == "s":
            continue
        print("    recording... Enter to stop")
        audio = record()
        name = f"{lang}_{number:02d}_mine.wav" if text else f"none_{lang}_{number:02d}.wav"
        sf.write(os.path.join(OUT, name), audio, RATE)
        level = 20 * np.log10(np.sqrt(np.mean(audio ** 2)) + 1e-9)
        print(f"    saved {len(audio) / RATE:.1f} s (average level {level:.0f} dBFS)\n")
        index.append({"file": name, "lang": lang, "condition": "mine" if text else "no_speech",
                      "ref": text})
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    print(f"{len(index)} recordings in {OUT}")


if __name__ == "__main__":
    main()
