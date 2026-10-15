"""Speech to text: Whisper, loaded once, and every clip through it.

The only module that imports faster-whisper — so the reader process, which never
imports it, keeps its own CUDA libraries to itself (see zero_flow.py).
"""
import logging
import os
import sys

import numpy as np
import soundfile as sf

# CTranslate2 (faster-whisper's engine) imports torch and transformers on import, for
# its model *converters* — about 6 s, on every start, for code this engine never runs.
# The import is optional (try/except ImportError) and only succeeds because the
# reader's voice needs both installed. Marking them unavailable for this one import
# makes the engine ready ~5 s sooner and keeps torch out of the dictation process.
# Guarded by tests/test_startup.py.
_skipped = [name for name in ("torch", "transformers") if name not in sys.modules]
sys.modules.update(dict.fromkeys(_skipped))      # None: "import X" raises ImportError
try:
    from faster_whisper import WhisperModel
    from faster_whisper.utils import download_model
finally:
    for _name in _skipped:
        sys.modules.pop(_name, None)                 # a later real import still works
from huggingface_hub.utils import logging as hf_logging

from zeroflow import personas, ui
from zeroflow.paths import TEMP_AUDIO_FILE
from zeroflow.settings import SAMPLE_RATE, WHISPER_COMPUTE_TYPE, WHISPER_DEVICE, WHISPER_MODEL_NAME
from zeroflow.text.language import ARABIC_LETTERS, plain_words
from zeroflow.vocabulary import load_vocabulary

# A first-run model download is an anonymous Hub request, which the Hub answers with a
# "set a HF_TOKEN" notice about rate limits. The models are public and fetched once;
# the notice is noise. (Every later boot reads the cache and asks the Hub nothing.)
hf_logging.set_verbosity_error()

model = None              # the faster-whisper model, loaded by load_whisper_model()
model_runtime = ""        # where it runs, e.g. "GPU · float16" — shown in the banner


# Whisper's retries at rising randomness when a decode looks unreliable. Its default
# goes up to 1.0, where the retry is close to guessing; this stops at 0.4.
TEMPERATURES = (0.0, 0.2, 0.4)


def resolve_whisper_model() -> str:
    """The Whisper model's folder on disk: straight from the local cache when it is
    there, downloaded only when it is not (the first run, or a new WHISPER_MODEL_NAME).

    Handing WhisperModel the bare name instead makes it ask the Hugging Face Hub for
    the latest revision on every boot, cached or not — a network call a local engine
    has no need for, and a stall at start-up whenever there is no internet."""
    if os.path.isdir(WHISPER_MODEL_NAME):
        return WHISPER_MODEL_NAME                # a local model folder was configured
    try:
        return download_model(WHISPER_MODEL_NAME, local_files_only=True)
    except FileNotFoundError:                    # huggingface_hub's LocalEntryNotFoundError
        logging.info(f"Whisper model '{WHISPER_MODEL_NAME}' is not cached yet; downloading it.")
        print(f"{ui.C_ACCENT}⬇️  Downloading the speech model '{WHISPER_MODEL_NAME}' "
              f"(first run only)...{ui.C_RESET}")
        return download_model(WHISPER_MODEL_NAME)


def load_whisper_model() -> WhisperModel:
    """Load faster-whisper on the GPU (unless WHISPER_DEVICE=cpu), verifying with a real
    inference so a missing CUDA library falls back to CPU at boot instead of crashing
    mid-dictation. Records where it ended up in `model_runtime`."""
    global model_runtime
    model_path = resolve_whisper_model()
    if WHISPER_DEVICE != "cpu":
        # Make any pip-installed CUDA DLLs (nvidia-cublas-cu12 / nvidia-cudnn-cu12) findable.
        for entry in sys.path:
            for lib in ("cublas", "cudnn"):
                bin_dir = os.path.join(entry, "nvidia", lib, "bin")
                if os.path.isdir(bin_dir):
                    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                    if hasattr(os, "add_dll_directory"):
                        os.add_dll_directory(bin_dir)
        try:
            m = WhisperModel(model_path, device="cuda", compute_type=WHISPER_COMPUTE_TYPE)
            # CTranslate2 loads the CUDA libs lazily on first inference, so force a tiny
            # real decode now — any GPU failure surfaces here and falls back cleanly.
            list(m.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), vad_filter=False)[0])
            model_runtime = f"GPU · {WHISPER_COMPUTE_TYPE}"
            logging.info(f"Whisper model active on CUDA ({WHISPER_COMPUTE_TYPE}).")
            return m
        except Exception as e:
            logging.warning(f"CUDA unavailable ({e}); falling back to CPU (int8).")
    m = WhisperModel(model_path, device="cpu", compute_type="int8")
    model_runtime = "CPU · int8"
    logging.info("Whisper model active on CPU (int8).")
    return m


def whisper_hint(language: str | None) -> str | None:
    """Whisper's hint (initial_prompt) for one language: text in that language only.

    Whisper reads the hint as the text that came just before, so its language and style
    carry over. Priming Arabic with the shared vocabulary — mostly Latin-script tech
    terms — raised character errors from ~38% to ~49% on the Arabic test clips and left
    the output unpunctuated. Arabic gets a short punctuated Arabic sentence plus any
    Arabic terms; English gets the Latin-script terms. Sorted, so the hint is the same
    from one run to the next.
    """
    vocab = sorted(load_vocabulary())
    arabic_terms = [w for w in vocab if ARABIC_LETTERS.search(w)]
    if language == "ar":
        return " ".join([personas.ARABIC_WHISPER_HINT] + (["، ".join(arabic_terms)] if arabic_terms else []))
    if language == "en":
        vocab = [w for w in vocab if not ARABIC_LETTERS.search(w)]
    return ", ".join(vocab) or None


# Whisper learned from subtitled videos, and a breath or a keystroke after you stop
# talking is where it writes how those videos end. Only these phrases are ever dropped,
# only at the very end, and only when the audio says they were not said.
STOCK_ENDINGS = sorted({tuple(plain_words(p)) for p in (
    "thank you", "thank you very much", "thank you so much", "thanks", "thanks a lot",
    "thank you for watching", "thanks for watching", "thank you for listening",
    "thanks for listening", "please subscribe", "subscribe to the channel",
    "have a good night", "have a nice day", "have a great day", "good night", "bye",
    "bye bye", "goodbye", "see you next time", "see you", "you",
    "شكرا", "شكرا لكم", "شكرا جزيلا", "شكرا للمشاهدة", "شكرا على المشاهدة",
    "شكرا لحسن الاستماع", "اشتركوا في القناة", "لا تنسوا الاشتراك في القناة",
    "ترجمة نانسي قنقر", "مع السلامة", "الى اللقاء",
)}, key=len, reverse=True)


# The tail counts as never said if it is this much quieter than the speech before it
# (a breath, typing, a room), or if Whisper's own confidence in its words is this low.
INVENTED_QUIETER_DB = 15
INVENTED_MAX_PROBABILITY = 0.5


# With nothing said before it, a stock phrase on audio quieter than this is a breath or
# a room: real speech, even far from the microphone, is louder.
INVENTED_ALONE_MAX_DBFS = -45


def _rms(audio: np.ndarray, spans: list[tuple[float, float]]) -> float:
    parts = [audio[int(s * SAMPLE_RATE):int(e * SAMPLE_RATE)] for s, e in spans]
    samples = np.concatenate([p for p in parts if len(p)] or [np.zeros(1, np.float32)])
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64)))) or 1e-9


def trim_invented_ending(words: list, audio: np.ndarray) -> list:
    """`words` (Whisper's, with timings and confidence) without a stock ending that was
    never said. `audio` is the clip as recorded, before any volume change.

    A known ending ("Thank you.", "شكرا للمشاهدة"…) is dropped only from the very end,
    and only if it sits on audio INVENTED_QUIETER_DB quieter than the speech before it,
    or Whisper scored its own words below INVENTED_MAX_PROBABILITY. If the phrase is all
    there is, it must be quieter than INVENTED_ALONE_MAX_DBFS or unsure. A clearly
    spoken "thank you" passes every one of these and stays."""
    tokens = [plain_words(w.word) for w in words]
    flat = [(i, t) for i, ts in enumerate(tokens) for t in ts]
    for phrase in STOCK_ENDINGS:
        if len(phrase) <= len(flat) and tuple(t for _, t in flat[-len(phrase):]) == phrase:
            cut = flat[-len(phrase)][0]
            break
    else:
        return words
    ending, said = words[cut:], words[:cut]
    level = _rms(audio, [(w.start, w.end) for w in ending])
    confidence = sum(w.probability for w in ending) / len(ending)
    if said:
        quieter_db = 20 * np.log10(_rms(audio, [(w.start, w.end) for w in said]) / level)
        invented = quieter_db >= INVENTED_QUIETER_DB or confidence < INVENTED_MAX_PROBABILITY
        evidence = f"{quieter_db:.0f} dB quieter than the speech, confidence {confidence:.2f}"
    else:
        dbfs = 20 * np.log10(level)
        invented = dbfs < INVENTED_ALONE_MAX_DBFS or confidence < INVENTED_MAX_PROBABILITY
        evidence = f"nothing said before it, {dbfs:.0f} dBFS, confidence {confidence:.2f}"
    if not invented:
        return words
    logging.info(f"Dropped an invented ending: {''.join(w.word for w in ending).strip()!r} "
                 f"({evidence}).")
    return said


def transcribe_clip(language: str, audio: np.ndarray | None = None) -> tuple[str | None, str | None]:
    """Decode TEMP_AUDIO_FILE → (text, language).

    `language` ('en' or 'ar') forces the output language — no detection, so it can
    never mishear English as Arabic. `audio` is the clip as recorded; with it, a stock
    ending nobody said is dropped (trim_invented_ending).

    Returns (None, None) when transcription failed — distinct from ("", lang), which
    means it ran and heard no speech. A failure on the graphics card (typically out of
    memory: Whisper, the voice and the AI model share it) retries the clip on the CPU.
    """
    def run(whisper):
        # condition_on_previous_text=False prevents repetition-loop hallucinations;
        # beam_size=5 gives steadier decoding on short clips; word timings are what
        # trim_invented_ending weighs.
        segments, _ = whisper.transcribe(
            TEMP_AUDIO_FILE, beam_size=5, vad_filter=True,
            condition_on_previous_text=False, language=language,
            initial_prompt=whisper_hint(language), word_timestamps=True,
            temperature=TEMPERATURES,
        )
        segments = list(segments)
        text = "".join(s.text for s in segments).strip()
        words = [w for s in segments if isinstance(s.words, (list, tuple)) for w in s.words]
        if audio is not None and words:
            kept = trim_invented_ending(words, audio)
            if len(kept) < len(words):
                text = "".join(w.word for w in kept).strip()
        return text, language

    try:
        return run(model)
    except Exception as e:
        if not model_runtime.startswith("GPU"):
            logging.error(f"Whisper transcription failed: {e}")
            return None, None
        logging.warning(f"Whisper failed on the graphics card ({e}); transcribing this clip on the CPU.")
    try:
        return run(cpu_fallback_model())
    except Exception as e:
        logging.error(f"Whisper transcription failed on the CPU too: {e}")
        return None, None
_cpu_model = None        # loaded on the first GPU failure, then kept for later ones


def cpu_fallback_model() -> WhisperModel:
    """A CPU copy of the speech model, for clips the graphics card could not take."""
    global _cpu_model
    if _cpu_model is None:
        _cpu_model = WhisperModel(resolve_whisper_model(), device="cpu", compute_type="int8")
        logging.info("Loaded a CPU copy of the speech model for graphics-card failures.")
    return _cpu_model


def transcribe_audio(audio: np.ndarray, language: str) -> tuple[str | None, str | None]:
    """One captured clip → (text, language), by exactly the steps every dictation
    takes. Kept apart from the hotkey path so tools/bench_stt.py measures the same
    thing you get."""
    recorded = audio
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak                     # normalise to full scale
    sf.write(TEMP_AUDIO_FILE, audio, SAMPLE_RATE)
    try:
        return transcribe_clip(language, recorded)
    finally:
        if os.path.exists(TEMP_AUDIO_FILE):
            os.remove(TEMP_AUDIO_FILE)
