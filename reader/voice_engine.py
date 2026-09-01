"""
Kokoro text-to-speech playback.

Audio is generated chunk by chunk and handed to a single playback worker thread, so
speech starts before the whole passage has been synthesised and can be cut off
instantly (`interrupt_audio`) without waiting for the generator to finish.

The pipeline — and the `torch` import behind it — is loaded lazily on the first
spoken word, not at import time, so startup stays instant.

**Device policy.** Kokoro uses the GPU when it has the process to itself, and the CPU
when it shares one with Whisper. That is not a preference, it is a hard requirement:
torch 2.5.1+cu121 bundles cuDNN 9.1 while CTranslate2 (Whisper) needs the pip-installed
cuDNN 9.23, Windows loads only one DLL per base name per process, and the loser
**segfaults the whole process** — in either load order, with no exception to catch.
Kokoro-82M on CPU synthesises at roughly 2.7x realtime and loads faster than it does
on GPU, so the merged engine gives up nothing measurable by forcing it there.
"""
import logging
import os
import queue
import threading
import warnings

import sounddevice as sd

import engine_ui as ui

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

# Kokoro-82M always synthesises at 24 kHz.
OUTPUT_SAMPLE_RATE = 24000
REPO_ID = "hexgrad/Kokoro-82M"
LANG_CODE = "a"                                  # 'a' = American English

# Menu label -> Kokoro voice id.
VOICES = {
    "American Female (Heart)": "af_heart",
    "American Female (Bella)": "af_bella",
    "British Female (Emma)": "bf_emma",
}
DEFAULT_VOICE = os.getenv("READER_VOICE", "af_heart")

# "auto" (GPU when available), "cpu", or "cuda". The merged engine overrides this to
# "cpu" via force_cpu() before the first read — see the module docstring.
DEVICE_POLICY = os.getenv("READER_DEVICE", "auto").strip().lower()
_forced_cpu_reason = None

current_voice = DEFAULT_VOICE
audio_queue = queue.Queue()
stop_playback = False

_pipeline = None
_pipeline_lock = threading.Lock()


def force_cpu(reason):
    """Pin Kokoro to the CPU whatever READER_DEVICE says. The merged engine calls this
    at boot: sharing a process with Whisper on the GPU is a segfault, not a slowdown,
    so this deliberately overrides the user's setting."""
    global _forced_cpu_reason
    _forced_cpu_reason = reason


def resolve_device():
    """Pick the device for Kokoro, honouring any hard override."""
    if _forced_cpu_reason:
        if DEVICE_POLICY == "cuda":
            logging.warning(f"READER_DEVICE=cuda ignored: {_forced_cpu_reason}")
        return "cpu"
    if DEVICE_POLICY == "cpu":
        return "cpu"
    import torch
    if DEVICE_POLICY == "cuda":
        return "cuda"
    return "cuda" if torch.cuda.is_available() else "cpu"


def get_pipeline():
    """Load Kokoro on first use (GPU when available, CPU otherwise) and cache it."""
    global _pipeline
    with _pipeline_lock:
        if _pipeline is None:
            from kokoro import KPipeline          # deliberately deferred — see the module docstring
            device = resolve_device()
            print(f"{ui.C_ACCENT}🔵 [TTS]{ui.C_RESET} Loading Kokoro voice model on {device}...")
            _pipeline = KPipeline(lang_code=LANG_CODE, device=device, repo_id=REPO_ID)
            logging.info(f"Kokoro TTS pipeline loaded on {device}.")
            print(f"{ui.C_GOOD}🔵 [TTS]{ui.C_RESET} Voice model ready.")
        return _pipeline


def _playback_worker():
    while True:
        item = audio_queue.get()
        if item == "STOP":
            sd.stop()
            with audio_queue.mutex:
                audio_queue.queue.clear()
        elif item is not None and not stop_playback:
            sd.play(item, OUTPUT_SAMPLE_RATE)
            sd.wait()


threading.Thread(target=_playback_worker, daemon=True).start()


def set_voice(new_voice):
    """Switch the active voice. Accepts a menu label or a raw Kokoro voice id."""
    global current_voice
    current_voice = VOICES.get(new_voice, new_voice)
    logging.info(f"Reader voice switched to {current_voice}.")
    print(f"\n{ui.C_ACCENT}🔵 [TTS]{ui.C_RESET} Voice switched to {current_voice}")


def stream_audio(text):
    """Synthesise `text` and queue it for playback, chunk by chunk."""
    global stop_playback
    stop_playback = False

    generator = get_pipeline()(text, voice=current_voice, speed=1.0)
    for _, _, audio in generator:
        if stop_playback:
            break
        if audio is not None:
            audio_queue.put(audio)


def interrupt_audio():
    """Cut playback off immediately and drop everything still queued."""
    global stop_playback
    stop_playback = True

    # 1. Instantly kill the active hardware audio (interrupts sd.wait).
    sd.stop()

    # 2. Flush the queue of any remaining generated chunks.
    with audio_queue.mutex:
        audio_queue.queue.clear()

    # 3. Send the final stop signal to reset the worker thread.
    audio_queue.put("STOP")
