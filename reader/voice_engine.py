"""
Kokoro text-to-speech playback.

Text is synthesised a batch of sentences at a time and handed to a single playback
worker thread, so speech starts after the first sentence rather than after the whole
passage, and can be cut off instantly (`interrupt_audio`) mid-way through.

The batching is not cosmetic. Kokoro renders one request into exactly one chunk, so
passing it a whole paragraph means silence until every word of it is rendered — a
measured 3.4-5.0 s on CPU. Per sentence, that wait becomes ~0.8 s and the remainder
renders while the first plays.

The pipeline — and the `torch` import behind it — is loaded lazily on the first
spoken word, not at import time, so startup stays instant.

**Device policy.** Kokoro uses the GPU when it has the process to itself, and the CPU
when it shares one with Whisper. That is not a preference, it is a hard requirement:
torch 2.5.1+cu121 bundles cuDNN 9.1 while CTranslate2 (Whisper) needs the pip-installed
cuDNN 9.23, Windows loads only one DLL per base name per process, and the loser
**segfaults the whole process** — in either load order, with no exception to catch.
CPU synthesis measures 3.6-5.2x realtime against 52-82x on GPU, so it stays ahead of
playback but has far less headroom; sentence batching plus `preload()` is what keeps
it feeling immediate. Run the halves as two processes if you want the voice on GPU.
"""
import logging
import os
import queue
import re
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

# Sentence-aligned batching, so speech starts after the first sentence instead of
# after the whole passage. Latin and Arabic sentence enders, plus a hard line break.
SENTENCE_SPLIT = re.compile(r'(?<=[.!?؟۔…])\s+|\n+')
# The first batch is kept short: it is the only one the listener waits on.
FIRST_BATCH_CHARS = int(os.getenv("READER_FIRST_BATCH_CHARS", 120))
BATCH_CHARS = int(os.getenv("READER_BATCH_CHARS", 300))

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


def preload():
    """Load the model and warm its kernels ahead of the first read.

    Called on a background thread at startup so the first press of the read key
    does not pay the ~13 s model load, plus a first-inference cost on top."""
    try:
        pipeline = get_pipeline()
        for _ in pipeline("Ready.", voice=current_voice, speed=1.0):
            pass                                 # discard: this is a warm-up only
        logging.info("Kokoro pipeline preloaded and warmed.")
    except Exception as e:
        logging.error(f"Kokoro preload failed (the first read will load it): {e}")


def _iter_batches(text, first_max=FIRST_BATCH_CHARS, batch_max=BATCH_CHARS):
    """Split text into sentence-aligned batches, the first one deliberately small.

    Kokoro renders a whole request as a single chunk, so a long passage produces no
    audio at all until the entire thing is synthesised — seconds of silence on CPU.
    Feeding it a sentence at a time means playback starts after the *first* sentence
    and the rest renders while that plays (CPU manages 3-5x realtime, comfortably
    ahead of playback). Later batches are larger, since per-call overhead matters
    more than latency once the audio is already flowing.
    """
    sentences = [s for s in SENTENCE_SPLIT.split(text.strip()) if s.strip()]
    if not sentences:
        return
    buffer, limit = "", first_max
    for sentence in sentences:
        if buffer and len(buffer) + len(sentence) + 1 > limit:
            yield buffer
            buffer, limit = sentence, batch_max
        else:
            buffer = f"{buffer} {sentence}".strip()
    if buffer:
        yield buffer


def stream_audio(text):
    """Synthesise `text` and queue it for playback, a batch of sentences at a time."""
    global stop_playback
    stop_playback = False

    pipeline = get_pipeline()
    for batch in _iter_batches(text):
        if stop_playback:
            break
        for _, _, audio in pipeline(batch, voice=current_voice, speed=1.0):
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
