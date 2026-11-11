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
honoured as written. (In one process with Whisper it could not use CUDA at all:
ARCHITECTURE.md §12.) A card that fails, loading or speaking, gives way to the CPU for
the rest of the run (`get_pipeline`, `_switch_to_cpu`).

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

from zeroflow import microphone, models, settings, signals, ui

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
# Read by huggingface_hub when it is first imported, which is later, inside get_pipeline.
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Kokoro-82M always synthesises at 24 kHz.
OUTPUT_SAMPLE_RATE = 24000
REPO_ID = "hexgrad/Kokoro-82M"
LANG_CODE = "a"                                  # 'a' = American English

DEFAULT_VOICE = settings.READER_VOICE

# "auto" (GPU when available), "cpu", or "cuda". Honoured under every launcher.
DEVICE_POLICY = settings.READER_DEVICE

# Sentence-aligned batching, so speech starts after the first sentence instead of
# after the whole passage. Latin and Arabic sentence enders, plus a hard line break.
SENTENCE_SPLIT = re.compile(r'(?<=[.!?؟۔…])\s+|\n+')
# Where a first sentence too long for the first batch may be split: after a comma,
# semicolon or colon, Latin or Arabic.
CLAUSE_SPLIT = re.compile(r'(?<=[,;:،؛])\s+')
# The first batch is kept short: it is the only one the listener waits on.
FIRST_BATCH_CHARS = 120     # measured tuning, not a choice (docs/settings-table.md)
BATCH_CHARS = 300

current_voice = DEFAULT_VOICE
# Rendering stays this many chunks ahead of the speaker, no more. Unbounded, a GPU
# rendered a whole 50k-character selection (51 minutes of speech) in 37 s and held
# all of it: 296 MB, about 6 MB per minute (measured in Phase 6). A chunk is one batch,
# up to ~20 s of speech, so four keep well ahead of playback on a CPU as well.
AHEAD_CHUNKS = 4
# Holds (generation, audio) pairs. interrupt_audio() bumps the generation, so every
# chunk rendered before the interrupt is recognisably stale and is never played.
audio_queue = queue.Queue(maxsize=AHEAD_CHUNKS)
_generation = 0
_rendering = False      # a read is still synthesising: more chunks are coming
# How often the playback worker checks for an interrupt while a chunk is playing, and
# how often a render waiting for room in the queue checks for one.
PLAYBACK_POLL_SECONDS = 0.01
QUEUE_POLL_SECONDS = 0.05
# One render at a time: a new read waits here until the one it interrupted has let go,
# which is within one chunk (QUEUE_POLL_SECONDS while waiting for room).
_render_lock = threading.Lock()

_pipeline = None
_pipeline_lock = threading.Lock()
# The device the loaded voice model runs on. Once the card has failed it is "cpu" for
# the rest of this run: retried, a failed card failed again on every F4 (Phase 6).
active_device = None

# The sounddevice index READER_OUTPUT names, or None for the Windows default. Resolved
# on the first chunk played; a device that fails mid-read makes it None for this run.
UNRESOLVED = object()
_output = UNRESOLVED


def resolve_device():
    """Pick the device for Kokoro from READER_DEVICE."""
    if DEVICE_POLICY == "cpu":
        return "cpu"
    import torch
    if torch.version.cuda is None:
        # A CPU-only torch wheel. requirements.txt cannot express the +cu126 index, so
        # a plain `pip install -r` can quietly fetch this one and speech silently
        # halves in speed with no error anywhere. Say so.
        logging.warning("This is a CPU-only build of torch, so the voice model cannot "
                        "use the GPU. Reinstall with: pip install torch==2.14.1+cu126 "
                        "--index-url https://download.pytorch.org/whl/cu126")
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
    Both come from the pinned revision (zeroflow.models), never the latest upload.
    """
    from huggingface_hub import hf_hub_download, try_to_load_from_cache
    revision = models.revision(REPO_ID)
    cached = try_to_load_from_cache(REPO_ID, filename, revision=revision)
    if isinstance(cached, str):                  # otherwise None / "known missing"
        return cached
    logging.info(f"Downloading {filename} from {REPO_ID} (first use only).")
    print(f"{ui.C_ACCENT}🔵 [TTS]{ui.C_RESET} Downloading {filename} (first use only)...")
    return hf_hub_download(REPO_ID, filename, revision=revision)


def _load(device):
    """Build the Kokoro pipeline on `device`."""
    # Deliberately deferred — see the module docstring.
    from huggingface_hub.utils import logging as hf_logging
    from kokoro import KModel, KPipeline
    # The Hub answers a download with an "unauthenticated request" notice. It is
    # about rate limits, irrelevant to a one-time download of a public model, and
    # huggingface_hub resets its own log level on import, so set it here.
    hf_logging.set_verbosity_error()
    print(f"{ui.C_ACCENT}🔵 [TTS]{ui.C_RESET} Loading Kokoro voice model on {device}...")
    model = KModel(repo_id=REPO_ID, config=_model_file("config.json"),
                   model=_model_file(KModel.MODEL_NAMES[REPO_ID])).to(device).eval()
    pipeline = KPipeline(lang_code=LANG_CODE, repo_id=REPO_ID, model=model)
    # espeak, the fallback for words outside Kokoro's dictionary, logs "words
    # count mismatch" whenever it splits a word differently — harmless, and
    # most of reader_debug.log. phonemizer resets this level each time it
    # creates a backend (just now, inside KPipeline), so it is set after.
    logging.getLogger("phonemizer").setLevel(logging.ERROR)
    logging.info(f"Kokoro TTS pipeline loaded on {device}.")
    print(f"{ui.C_GOOD}🔵 [TTS]{ui.C_RESET} Voice model ready.")
    return pipeline


def get_pipeline():
    """Load Kokoro on first use (GPU when available, CPU otherwise) and cache it. A card
    that fails to load it gives way to the CPU for the rest of this run."""
    global _pipeline, active_device
    with _pipeline_lock:
        if _pipeline is None:
            device = resolve_device()
            try:
                _pipeline = _load(device)
            except Exception as e:
                if device == "cpu":
                    raise
                logging.warning(f"The voice model failed to load on the graphics card ({e}). "
                                f"The Reader uses the CPU for the rest of this run.")
                device = "cpu"
                _pipeline = _load(device)
            active_device = device
        return _pipeline


def _switch_to_cpu(error, failed):
    """The card failed while speaking: replace its pipeline with a CPU one, once.
    False when the pipeline that failed was already on the CPU (the caller raises)."""
    global _pipeline, active_device
    with _pipeline_lock:
        if _pipeline is not failed:
            return True                          # another read switched already
        if active_device == "cpu":
            return False
        logging.warning(f"The graphics card failed while the Reader was speaking ({error}). "
                        f"The Reader uses the CPU for the rest of this run.")
        _pipeline = _load("cpu")
        active_device = "cpu"
        return True


def _render(batch, voice_id, speed):
    """The audio chunks of one batch. When the card fails part-way, the batch is rendered
    again on the CPU and only the chunks not yet given are given."""
    given = 0
    while True:
        pipeline = get_pipeline()
        try:
            for index, (_, _, audio) in enumerate(pipeline(batch, voice=_voice(voice_id),
                                                           speed=speed)):
                if index >= given:
                    given += 1
                    yield audio
            return
        except Exception as e:
            if not _switch_to_cpu(e, pipeline):
                raise


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
            _play(audio)
            stream = sd.get_stream()
            while stream.active:
                if generation != _generation:
                    stream.abort()               # cut off now rather than drain the buffer
                    break
                time.sleep(PLAYBACK_POLL_SECONDS)
            sd.stop()                            # closes the stream
            if audio_queue.empty() and not _rendering:
                signals.set_reading(False)       # the overlay's "Reading" ends
        except Exception as e:
            # One bad chunk (a device unplugged mid-read, say) must not end this thread:
            # the reader would carry on "speaking" into a queue nobody plays.
            logging.error(f"Reader playback failed: {e}")


def _output_device():
    """The sounddevice index for READER_OUTPUT, or None for the Windows default — also
    what a name that is not plugged in falls back to, said once, for this run."""
    global _output
    if _output is UNRESOLVED:
        _output = None
        if settings.READER_OUTPUT:
            try:
                index, fell_back = microphone.resolve(settings.READER_OUTPUT, sd.query_devices(),
                                                      sd.default.hostapi, output=True)
            except Exception:
                index, fell_back = None, True
            if fell_back:
                logging.warning(f"The Reader output '{settings.READER_OUTPUT}' is not connected; "
                                f"using the Windows default for this run.")
            _output = index
    return _output


def _play(audio):
    """Start one chunk on the chosen output. A chosen output that fails (unplugged) gives
    way to the Windows default for the rest of this run, starting with this chunk."""
    global _output
    device = _output_device()
    try:
        sd.play(audio, OUTPUT_SAMPLE_RATE, device=device)
    except Exception as e:
        if device is None:
            raise
        logging.warning(f"The Reader output failed ({e}); using the Windows default "
                        f"for the rest of this run.")
        _output = None
        sd.play(audio, OUTPUT_SAMPLE_RATE, device=None)


threading.Thread(target=_playback_worker, daemon=True).start()


def preload():
    """Load the model and warm its kernels ahead of the first read.

    Called on a background thread at startup so the first press of the read key
    does not pay the ~13 s model load, plus a first-inference cost on top."""
    try:
        for _ in _render("Ready.", current_voice, 1.0):
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

    A first sentence longer than `first_max` is the one exception to whole sentences:
    it is split after a comma, so a long opening is not seconds of silence on a CPU
    (223 characters: 3.4 s to the first sound, 2.0 s split).
    """
    sentences = [s for s in SENTENCE_SPLIT.split(text.strip()) if s.strip()]
    if not sentences:
        return
    sentences[:1] = _split_long_first(sentences[0], first_max)
    buffer, limit = "", first_max
    for sentence in sentences:
        if buffer and len(buffer) + len(sentence) + 1 > limit:
            yield buffer
            buffer, limit = sentence, batch_max
        else:
            buffer = f"{buffer} {sentence}".strip()
    if buffer:
        yield buffer


def _split_long_first(sentence, first_max):
    """[sentence], or — when it is longer than `first_max` and has clause marks —
    [as many leading clauses as fit (at least one), the rest of the sentence]."""
    clauses = CLAUSE_SPLIT.split(sentence)
    if len(sentence) <= first_max or len(clauses) == 1:
        return [sentence]
    head = clauses.pop(0)
    while clauses and len(head) + 1 + len(clauses[0]) <= first_max:
        head = f"{head} {clauses.pop(0)}"
    return [head, " ".join(clauses)] if clauses else [sentence]


def stream_audio(text, generation=None):
    """Synthesise `text` and queue it for playback, a batch of sentences at a time.
    Stops rendering as soon as interrupt_audio() is called — or has been, since the
    read that owns `generation` began (interrupt_audio's return value).

    Returns only once the last chunk is queued, which with AHEAD_CHUNKS is near the end
    of the speech: the caller must not hold the read key's lock through it."""
    global _rendering
    if generation is None:
        generation = _generation
    with _render_lock:                           # the read this one interrupted lets go
        if generation != _generation:
            return
        get_pipeline()
        _rendering = True
        signals.set_reading(True)
        try:
            for batch in _iter_batches(text):
                for audio in _render(batch, current_voice, settings.READER_SPEED):
                    if generation != _generation:
                        return
                    if audio is not None and not _queue_chunk(generation, audio):
                        return
        finally:
            _rendering = False
            if audio_queue.empty() and generation != _generation:
                signals.set_reading(False)


def _queue_chunk(generation, audio):
    """Queue one chunk, waiting while AHEAD_CHUNKS are queued already. False when the
    read is interrupted while it waits: the chunk is dropped and the render ends."""
    while generation == _generation:
        try:
            audio_queue.put((generation, audio), timeout=QUEUE_POLL_SECONDS)
            return True
        except queue.Full:
            pass
    return False


def current_generation():
    return _generation


def interrupt_audio():
    """Cut playback off immediately and drop everything still queued.

    Safe to call from any thread. It never calls sounddevice itself — see
    _playback_worker for why — it only marks everything queued so far as stale.
    Returns the new generation: a read that passes it to stream_audio is dropped if
    anything interrupts in between (dictation starting while the text is cleaned)."""
    global _generation
    _generation += 1
    generation = _generation
    signals.set_reading(False)
    with audio_queue.mutex:                      # free the memory now; the worker
        audio_queue.queue.clear()                # would skip these chunks anyway
    return generation
