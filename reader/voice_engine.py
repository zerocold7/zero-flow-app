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

**Device policy.** The reader always runs in its own process — standalone, or as the
child `zero_flow.py` spawns — so it can hold CUDA freely and `READER_DEVICE` is
honoured as written.

That isolation is deliberate. Hosting this half and Whisper as threads in *one*
process would force the voice onto the CPU: torch 2.5.1+cu121 bundles cuDNN 9.1 while
CTranslate2 (Whisper) needs the pip-installed cuDNN 9.23, Windows loads only one DLL
per base name per process, and the loser **segfaults the whole process** — in either
load order, with no exception to catch. CPU synthesis measures 3.6-5.2x realtime
against 52-82x on GPU, so it stays ahead of playback but with far less headroom.

**Model files.** The model, its config and each voice are read straight from the local
Hugging Face cache, and fetched from the Hub only when missing (the first run, or a
voice picked for the first time). Letting Kokoro fetch them itself costs four network
requests on every start even with everything cached — see `_model_file`.
"""
import logging
import os
import queue
import re
import threading
import time
import warnings

import sounddevice as sd

import engine_ui as ui

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
# Read by huggingface_hub when it is first imported, which is later, inside get_pipeline.
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

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

# "auto" (GPU when available), "cpu", or "cuda". Honoured under every launcher.
DEVICE_POLICY = os.getenv("READER_DEVICE", "auto").strip().lower()

# Sentence-aligned batching, so speech starts after the first sentence instead of
# after the whole passage. Latin and Arabic sentence enders, plus a hard line break.
SENTENCE_SPLIT = re.compile(r'(?<=[.!?؟۔…])\s+|\n+')
# The first batch is kept short: it is the only one the listener waits on.
FIRST_BATCH_CHARS = int(os.getenv("READER_FIRST_BATCH_CHARS", 120))
BATCH_CHARS = int(os.getenv("READER_BATCH_CHARS", 300))

current_voice = DEFAULT_VOICE
# Holds (generation, audio) pairs. interrupt_audio() bumps the generation, so every
# chunk rendered before the interrupt is recognisably stale and is never played.
audio_queue = queue.Queue()
_generation = 0
# How often the playback worker checks for an interrupt while a chunk is playing.
PLAYBACK_POLL_SECONDS = 0.01

_pipeline = None
_pipeline_lock = threading.Lock()


def resolve_device():
    """Pick the device for Kokoro from READER_DEVICE."""
    if DEVICE_POLICY == "cpu":
        return "cpu"
    import torch
    if torch.version.cuda is None:
        # A CPU-only torch wheel. requirements.txt cannot express the +cu121 index, so
        # a plain `pip install -r` can quietly fetch this one and speech silently
        # halves in speed with no error anywhere. Say so.
        logging.warning("This is a CPU-only build of torch, so the voice model cannot "
                        "use the GPU. Reinstall with: pip install torch==2.5.1+cu121 "
                        "--index-url https://download.pytorch.org/whl/cu121")
        return "cpu"
    if DEVICE_POLICY == "cuda":
        return "cuda"
    return "cuda" if torch.cuda.is_available() else "cpu"


def _model_file(filename):
    """Local path to one of Kokoro's files on the Hugging Face Hub.

    Taken straight from the local cache when it is there; downloaded only when it is
    not. Left to itself, Kokoro calls hf_hub_download for every file on every start,
    and each call asks the Hub whether the file changed — four requests before the
    first word, cached or not. That made a local-only engine phone home on each boot,
    stalled start-up without internet, and drew the Hub's anonymous-request warning
    ("set a HF_TOKEN") into reader_debug.log. The model is public: no token needed.
    """
    from huggingface_hub import hf_hub_download, try_to_load_from_cache
    cached = try_to_load_from_cache(REPO_ID, filename)
    if isinstance(cached, str):                  # otherwise None / "known missing"
        return cached
    logging.info(f"Downloading {filename} from {REPO_ID} (first use only).")
    print(f"{ui.C_ACCENT}🔵 [TTS]{ui.C_RESET} Downloading {filename} (first use only)...")
    return hf_hub_download(REPO_ID, filename)


def get_pipeline():
    """Load Kokoro on first use (GPU when available, CPU otherwise) and cache it."""
    global _pipeline
    with _pipeline_lock:
        if _pipeline is None:
            # Deliberately deferred — see the module docstring.
            from huggingface_hub.utils import logging as hf_logging
            from kokoro import KModel, KPipeline
            # The Hub answers a download with an "unauthenticated request" notice. It is
            # about rate limits, irrelevant to a one-time download of a public model, and
            # huggingface_hub resets its own log level on import, so set it here.
            hf_logging.set_verbosity_error()
            device = resolve_device()
            print(f"{ui.C_ACCENT}🔵 [TTS]{ui.C_RESET} Loading Kokoro voice model on {device}...")
            model = KModel(repo_id=REPO_ID, config=_model_file("config.json"),
                           model=_model_file(KModel.MODEL_NAMES[REPO_ID])).to(device).eval()
            _pipeline = KPipeline(lang_code=LANG_CODE, repo_id=REPO_ID, model=model)
            # espeak, the fallback for words outside Kokoro's dictionary, logs "words
            # count mismatch" whenever it splits a word differently — harmless, and
            # most of reader_debug.log. phonemizer resets this level each time it
            # creates a backend (just now, inside KPipeline), so it is set after.
            logging.getLogger("phonemizer").setLevel(logging.ERROR)
            logging.info(f"Kokoro TTS pipeline loaded on {device}.")
            print(f"{ui.C_GOOD}🔵 [TTS]{ui.C_RESET} Voice model ready.")
        return _pipeline


def _voice(voice_id):
    """The loaded voice for a Kokoro voice id, read from the local cache when present.
    Handing KPipeline a bare id would make it ask the Hub about the file every start."""
    return get_pipeline().load_single_voice(_model_file(f"voices/{voice_id}.pt"))


def _playback_worker():
    """Play queued chunks in order. This is the only thread that touches sounddevice.

    sd.play / sd.wait / sd.stop share one module-global stream and are not thread-safe.
    An sd.stop() from another thread while this one sat in sd.wait() had both threads
    close the same PortAudio stream — a double free that killed the reader with
    0xC0000005 / 0xC0000374, typically on Esc or when dictation started mid-read. So
    interrupt_audio() only bumps the generation, and this thread notices within
    PLAYBACK_POLL_SECONDS and stops the stream itself.
    """
    while True:
        generation, audio = audio_queue.get()
        if generation != _generation:
            continue                             # rendered before an interrupt: drop it
        try:
            sd.play(audio, OUTPUT_SAMPLE_RATE)
            stream = sd.get_stream()
            while stream.active:
                if generation != _generation:
                    stream.abort()               # cut off now rather than drain the buffer
                    break
                time.sleep(PLAYBACK_POLL_SECONDS)
            sd.stop()                            # closes the stream
        except Exception as e:
            # One bad chunk (a device unplugged mid-read, say) must not end this thread:
            # the reader would carry on "speaking" into a queue nobody plays.
            logging.error(f"Reader playback failed: {e}")


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
        for _ in pipeline("Ready.", voice=_voice(current_voice), speed=1.0):
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
    """Synthesise `text` and queue it for playback, a batch of sentences at a time.
    Stops rendering as soon as interrupt_audio() is called."""
    generation = _generation
    pipeline = get_pipeline()
    voice = _voice(current_voice)
    for batch in _iter_batches(text):
        for _, _, audio in pipeline(batch, voice=voice, speed=1.0):
            if generation != _generation:
                return
            if audio is not None:
                audio_queue.put((generation, audio))


def interrupt_audio():
    """Cut playback off immediately and drop everything still queued.

    Safe to call from any thread. It never calls sounddevice itself — see
    _playback_worker for why — it only marks everything queued so far as stale."""
    global _generation
    _generation += 1
    with audio_queue.mutex:                      # free the memory now; the worker
        audio_queue.queue.clear()                # would skip these chunks anyway
