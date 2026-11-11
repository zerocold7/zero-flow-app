"""Smoke check: the engine's real parts working on this PC, end to end, without hotkeys.

    venv\\Scripts\\python.exe tools\\smoke_check.py

Uses the settings in settings.json, like the engine. Each part prints PASS or FAIL; the exit
code is the number of failures. Nothing is typed, pasted or played aloud:
  1. settings     settings.json reads with no reported problems
  2. devices      a microphone and a speaker are present
  3. speech       Whisper transcribes the recordings in tools/bench/mine (English and
                  Arabic), where it ran (graphics card or processor)
  4. AI           the AI provider answers a Polish, then frees its memory
  5. voice        the reader's voice synthesises a sentence, where it ran

Logs go to a temporary folder (removed afterwards), not the program folder.
"""
import os
import sys
import time
import traceback
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from zeroflow.paths import use_temporary_log_dir  # noqa: E402

use_temporary_log_dir("zeroflow-smoke-")

import numpy as np  # noqa: E402

CLIPS = {"en": "en_01_mine.wav", "ar": "ar_09_mine.wav"}
failures = 0


def part(name):
    """Run the decorated check now and print PASS/FAIL with how long it took."""
    def run(check):
        global failures
        started = time.time()
        try:
            detail = check()
            sys.stdout.write("\r" + " " * 40 + "\r")     # wipe the AI spinner's line
            print(f"PASS  {name:<9} {time.time() - started:5.1f} s  {detail}")
        except Exception as e:
            failures += 1
            print(f"FAIL  {name:<9} {time.time() - started:5.1f} s  {e}")
            traceback.print_exc(limit=3)
    return run


def read_clip(path):
    with wave.open(path) as w:
        assert w.getframerate() == 16000 and w.getsampwidth() == 2 and w.getnchannels() == 1
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768


@part("settings")
def _():
    from zeroflow import settings
    assert not settings.problems, "; ".join(settings.problems)
    return f"provider {settings.AI_PROVIDER}, Whisper {settings.WHISPER_MODEL_NAME}"


@part("devices")
def _():
    import sounddevice as sd
    mic, speaker = sd.query_devices(kind="input"), sd.query_devices(kind="output")
    return f"mic '{mic['name']}', speaker '{speaker['name']}'"


@part("speech")
def _():
    from zeroflow import stt
    from zeroflow.text.language import ARABIC_LETTERS, LATIN_LETTERS
    stt.model = stt.load_whisper_model()
    heard = []
    for lang, name in CLIPS.items():
        path = os.path.join(ROOT, "tools", "bench", "mine", name)
        if not os.path.isfile(path):
            heard.append(f"{lang}: no clip")
            continue
        text, _ = stt.transcribe_audio(read_clip(path), lang)
        letters = ARABIC_LETTERS if lang == "ar" else LATIN_LETTERS
        assert text and letters.search(text), f"{lang} clip gave {text!r}"
        heard.append(f"{lang}: {len(text)} chars")
    return f"{stt.model_runtime}; " + ", ".join(heard)


@part("AI")
def _():
    from zeroflow import llm, personas
    answer = llm.ask_ai("um so the meeting is uh moved to thursday", None,
                        personas.STANDARD_SYSTEM_PROMPT, timeout=120)
    assert answer and "thursday" in answer.lower(), f"answer {answer!r}"
    freed = llm.unload_ai()
    return f"{llm.model_name()}: {answer!r}; memory freed: {freed}"


@part("voice")
def _():
    from reader import voice_engine
    pipeline = voice_engine.get_pipeline()
    voice = voice_engine._voice(voice_engine.current_voice)
    samples = sum(len(audio) for _, _, audio in
                  pipeline("This is a short check of the voice.", voice=voice)
                  if audio is not None)
    assert samples > voice_engine.OUTPUT_SAMPLE_RATE, f"only {samples} samples"
    return (f"{samples / voice_engine.OUTPUT_SAMPLE_RATE:.1f} s of speech on "
            f"{voice_engine.resolve_device()}")


print(f"\n{failures} failed" if failures else "\nall parts work")
sys.exit(failures)
