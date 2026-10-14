"""Make the speech-recognition benchmark's test clips (tools/bench/clips/, git-ignored).

    venv\\Scripts\\python.exe tools\\bench\\make_clips.py

Every clip is synthetic and made the same way on every run (fixed noise seeds), so
two benchmark runs differ only by what changed in the engine:

  * English sentences spoken by Kokoro (the reader's voices), Arabic by espeak-ng —
    robotic, but the only Arabic voice available offline;
  * each sentence three ways — "clean"; "tail", followed by 4 s of room noise (where
    Whisper invents "Thank you." and the like); and "quiet", spoken softly, so the
    engine's volume boost turns the background up with it;
  * clips with no speech at all — silence, hum, clicks, quiet and loud room noise —
    which should come out empty.

Some sentences really do end in "thank you" or "شكرا": a filter for invented endings
must leave those alone. Nothing here downloads anything; the voices come from the
local model cache.
"""
import ctypes
import json
import os
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")         # cached voices only, no Hub requests

import numpy as np
import soundfile as sf

RATE = 16_000
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clips")

ENGLISH = [
    ("af_heart", "Please send the updated report to the team before Friday afternoon."),
    ("am_michael", "I pushed the fix to GitHub and the tests are passing now."),
    ("bf_emma", "Can we move tomorrow's meeting to ten thirty instead of nine?"),
    ("af_heart", "The Docker container keeps restarting because the port is already in use."),
    ("am_michael", "Thanks for the quick reply, I will review the document tonight."),
    ("bf_emma", "Remind me to call the bank about the new Visa card next week."),
    ("af_heart", "The model runs on the graphics card, so it should be much faster."),
    ("am_michael", "Let's keep the first version simple and add the settings window later."),
    ("bf_emma", "I couldn't find the file, so I created a new folder for the project."),
    ("af_heart", "Ollama is running in the background with the Gemma model loaded."),
    ("am_michael", "That was very helpful, thank you so much."),
    ("bf_emma", "The installer should ask before it deletes any of your personal data."),
]

ARABIC = [
    "أرسل التقرير المحدث إلى الفريق قبل يوم الجمعة.",
    "هل يمكننا تأجيل الاجتماع إلى الساعة العاشرة صباحا؟",
    "قمت بتحديث البرنامج وأصبحت جميع الاختبارات ناجحة.",
    "يجب أن نراجع الميزانية الجديدة قبل نهاية الشهر.",
    "شكرا جزيلا على مساعدتك في هذا المشروع.",
    "الطقس اليوم جميل ونريد الخروج إلى الحديقة.",
    "سأتصل بك بعد أن أنتهي من كتابة الرسالة.",
    "يعمل النموذج على بطاقة الرسومات لذلك هو أسرع بكثير.",
    "لم أجد الملف فأنشأت مجلدا جديدا للمشروع.",
    "من فضلك ذكرني بموعد الطبيب يوم الأحد القادم.",
    "نحتاج إلى اختبار البرنامج على حاسوب جديد قبل الإصدار.",
    "أتمنى لكم يوما سعيدا وإلى اللقاء.",
]


# ---------------------------------------------------------------- signal helpers
def db(level):
    return 10 ** (level / 20)


def resample(x, rate):
    """Band-limited resampling to RATE through the FFT (no scipy in the engine)."""
    if rate == RATE:
        return x.astype(np.float32)
    n = int(round(len(x) * RATE / rate))
    spectrum = np.fft.rfft(x)
    return (np.fft.irfft(spectrum[: n // 2 + 1], n) * (n / len(x))).astype(np.float32)


def pink_noise(seconds, level_db, seed):
    """1/f noise like a quiet room or a fan, scaled to `level_db` dBFS RMS."""
    rng = np.random.default_rng(seed)
    n = int(seconds * RATE)
    spectrum = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1 / RATE)
    spectrum /= np.sqrt(np.maximum(freqs, 20.0))
    noise = np.fft.irfft(spectrum, n)
    return (noise / np.sqrt(np.mean(noise ** 2)) * db(level_db)).astype(np.float32)


def at_peak(x, level_db):
    return (x / np.max(np.abs(x)) * db(level_db)).astype(np.float32)


# ---------------------------------------------------------------- voices
def kokoro_speech():
    from kokoro import KPipeline
    pipelines = {}
    for voice, text in ENGLISH:
        lang = "b" if voice.startswith("b") else "a"
        if lang not in pipelines:
            pipelines[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
        chunks = [np.asarray(audio, dtype=np.float32)
                  for _, _, audio in pipelines[lang](text, voice=voice)]
        yield text, resample(np.concatenate(chunks), 24_000)


def espeak_speech():
    import espeakng_loader
    lib = ctypes.cdll.LoadLibrary(espeakng_loader.get_library_path())
    samples = []
    callback_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short),
                                     ctypes.c_int, ctypes.c_void_p)

    def collect(wav, count, events):
        if wav and count > 0:
            samples.append(np.ctypeslib.as_array(wav, (count,)).copy())
        return 0

    keep_alive = callback_type(collect)
    lib.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    data = espeakng_loader.get_data_path().encode()
    rate = lib.espeak_Initialize(2, 0, data, 0)          # 2 = AUDIO_OUTPUT_SYNCHRONOUS
    if rate <= 0:
        rate = lib.espeak_Initialize(2, 0, os.path.dirname(data), 0)
    lib.espeak_SetSynthCallback(keep_alive)
    lib.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
    if lib.espeak_SetVoiceByName(b"ar") != 0:
        sys.exit("espeak-ng has no Arabic voice here")
    lib.espeak_SetParameter(1, 150, 0)                   # rate, words per minute
    lib.espeak_Synth.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint, ctypes.c_int,
                                 ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    for text in ARABIC:
        samples.clear()
        raw = text.encode("utf-8")
        lib.espeak_Synth(raw, len(raw) + 1, 0, 0, 0, 1, None, None)   # 1 = espeakCHARS_UTF8
        lib.espeak_Synchronize()
        yield text, resample(np.concatenate(samples).astype(np.float32) / 32768, rate)


# ---------------------------------------------------------------- clips
def conditions(speech, seed):
    """The three ways each sentence is heard."""
    floor = lambda s, k: pink_noise(s, -65, seed * 10 + k)
    loud = at_peak(speech, -3)
    clean = np.concatenate([floor(0.25, 1), loud + floor(len(loud) / RATE, 2), floor(0.6, 3)])
    tail = np.concatenate([floor(0.25, 4), loud + floor(len(loud) / RATE, 5),
                           pink_noise(4.0, -48, seed * 10 + 6)])
    soft = at_peak(speech, -30)
    quiet = np.concatenate([pink_noise(0.25, -58, seed * 10 + 7),
                            soft + pink_noise(len(soft) / RATE, -58, seed * 10 + 8),
                            pink_noise(3.0, -58, seed * 10 + 9)])
    # What really follows a sentence before the key is pressed: a breath out, or typing.
    # Short sounds like these pass the voice filter as "speech" — and alone at the end
    # of a clip, they are where Whisper writes "Thank you."
    breath = np.concatenate([floor(0.25, 1), loud + floor(len(loud) / RATE, 2), floor(1.2, 7),
                             breath_sound(seed), floor(1.0, 8)])
    typing = np.concatenate([floor(0.25, 1), loud + floor(len(loud) / RATE, 2), floor(0.8, 9),
                             keystrokes(2.5, seed)])
    return {"clean": clean, "tail": tail, "quiet": quiet, "breath": breath, "typing": typing}


def breath_sound(seed):
    """A breath out: 0.6 s of breathy noise, rising and falling, about -28 dBFS."""
    n = int(0.6 * RATE)
    noise = pink_noise(0.6, -20, seed * 10 + 11)
    envelope = np.sin(np.linspace(0, np.pi, n)) ** 2
    return (noise * envelope * db(-8)).astype(np.float32)


def keystrokes(seconds, seed):
    """Typing: sharp clicks a few times a second over a quiet room."""
    out = pink_noise(seconds, -62, seed * 10 + 12)
    rng = np.random.default_rng(seed * 10 + 13)
    for start in np.cumsum(rng.uniform(0.12, 0.35, int(seconds * 5)) * RATE).astype(int):
        if start + 300 < len(out):
            out[start:start + 300] += (rng.standard_normal(300) * np.exp(-np.arange(300) / 40)
                                       * db(-22)).astype(np.float32)
    return out


def no_speech():
    t = np.arange(int(4.0 * RATE)) / RATE
    hum = sum(np.sin(2 * np.pi * 50 * k * t) / k for k in (1, 2, 3)).astype(np.float32)
    clicks = pink_noise(4.0, -62, 901)
    rng = np.random.default_rng(902)
    for start in rng.integers(0, len(clicks) - 400, 14):
        burst = rng.standard_normal(400) * np.exp(-np.arange(400) / 60) * db(-25)
        clicks[start:start + 400] += burst.astype(np.float32)
    return {
        "silence": np.zeros(int(3.0 * RATE), np.float32),
        "noise_floor": pink_noise(3.0, -65, 903),
        "room_noise": pink_noise(4.0, -45, 904),
        "loud_noise": pink_noise(4.0, -30, 905),
        "hum": at_peak(hum, -35) + pink_noise(4.0, -60, 906),
        "clicks": clicks,
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    index = []
    sources = [("en", kokoro_speech()), ("ar", espeak_speech())]
    for lang, speech in sources:
        for number, (text, audio) in enumerate(speech, 1):
            for condition, clip in conditions(audio, seed=number + (0 if lang == "en" else 100)).items():
                name = f"{lang}_{number:02d}_{condition}.wav"
                sf.write(os.path.join(OUT, name), clip, RATE)
                index.append({"file": name, "lang": lang, "condition": condition, "ref": text})
            print(f"{lang} {number:02d}  {len(audio) / RATE:4.1f} s  {text}")
    for name, clip in no_speech().items():
        sf.write(os.path.join(OUT, f"none_{name}.wav"), clip, RATE)
        for lang in ("en", "ar"):                            # each key is tried on them
            index.append({"file": f"none_{name}.wav", "lang": lang, "condition": "no_speech",
                          "ref": ""})
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    print(f"{len(index)} test cases in {OUT}")


if __name__ == "__main__":
    main()
