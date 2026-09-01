"""
Kokoro text-to-speech playback.

Audio is generated chunk by chunk and handed to a single playback worker thread, so
speech starts before the whole passage has been synthesised and can be cut off
instantly (`interrupt_audio`) without waiting for the generator to finish.

The pipeline — and the `torch` import behind it — is loaded lazily on the first
spoken word, not at import time. That keeps startup instant, and it keeps `torch`
out of the process until it is actually needed (which matters for the single-process
merge later: CTranslate2 and torch ship the same CUDA DLL names, and whichever loads
first wins for the whole process).
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

current_voice = DEFAULT_VOICE
audio_queue = queue.Queue()
stop_playback = False

_pipeline = None
_pipeline_lock = threading.Lock()


def get_pipeline():
    """Load Kokoro on first use (GPU when available, CPU otherwise) and cache it."""
    global _pipeline
    with _pipeline_lock:
        if _pipeline is None:
            import torch                          # deliberately deferred — see the module docstring
            from kokoro import KPipeline
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
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
