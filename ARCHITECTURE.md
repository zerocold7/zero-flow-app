# Zero- Flow — Architecture & Behaviour Guide

A practical map of what the engine does, how it should behave, and where each piece
lives in the code. Read this before changing `local_flow.py` or `reader/`.

---

## 1. What it is
Two background Windows processes that move text and speech in opposite directions:

- **Flow** (`local_flow.py`) turns speech into typed text in whatever app has focus.
  You press a hotkey, talk, press again — the words appear at your cursor.
- **Reader** (`reader/`) turns highlighted text into speech. You press `F4` and a
  local voice reads the selection aloud.

Both are **bilingual-aware**, run **fully locally** (no cloud), and can optionally use
a local LLM to clean up or translate text.

| File | Responsibility |
|------|----------------|
| `flow_core.py`  | **Shared:** paths, `.env` config, rotating debug log, learned vocabulary, the single Ollama client |
| `personas.py`   | **Shared:** static data — LLM prompts, base vocabulary, voice macros, punctuation, pronunciation |
| `engine_ui.py`  | **Shared:** console UI, beeps, Windows toasts, system-tray + window icon |
| `flow_signals.py` | **Shared:** Windows named events that keep the two halves off each other's toes |
| `local_flow.py` | Flow: hotkeys, audio capture, transcription, refinement, injection |
| `reader/`       | Reader: `app.py` (the half itself), `clipboard_tool.py`, `text_cleaner.py`, `voice_engine.py` |
| `zero_flow.py`  | The supervisor: runs dictation and hosts the reader as a child sharing its console |
| `check_hardware.py` | Standalone (standard library only): detects the GPU/RAM, picks a hardware tier, writes its settings into `.env` |
| `presets/`      | One `.env` fragment per hardware tier — the model and device settings `check_hardware.py` applies |
| `docs/`         | User guides: install, hardware & tuning, FAQ, the beginner walkthrough (English + Arabic) |
| `tools/`        | Rebuild the generated guides (the English and Arabic printable PDFs) from their Markdown — see `tools/README.md` |
| `tests/`        | `unittest` tests, run in the venv: text logic, recording and AI failure paths, playback threading, vocabulary and history files, process supervision (`.\venv\Scripts\python.exe -m unittest discover -s tests -t .`) |

**How they are hosted.** `zero_flow.py` is a supervisor, not a merge: it runs the
dictation half in its own process and launches the reader as a **child process**,
started without `CREATE_NEW_CONSOLE` so Windows hands it the parent's console. The
child prints into the same window and owns the single tray icon, which is why the
pair looks like one program while remaining two.

| Entry point | Processes | Voice model | Notes |
|-------------|-----------|-------------|-------|
| `zero_flow.py` | 2 (parent + child) | GPU | One window, one tray icon, crash isolation |
| `local_flow.py` + `reader/` | 2 | GPU | The same pair, two visible windows |

Separate processes are not a compromise here, they are the requirement: hosting both
halves as threads in one process forces the voice model onto the CPU, because Whisper
and Kokoro cannot both initialise CUDA in one address space (§12). The child owns the
tray because every control in that menu — voice, smart cleaning, suspend — toggles
state that lives in the reader; a parent-owned menu would need a command channel for
each one. The only signal that flows back is `EXIT`.

The resources they would fight over — the microphone, the clipboard, and who gets to
quit — are coordinated with named Windows objects in `flow_signals.py`. They work the
same whether the halves are under `zero_flow.py` or started separately:

| Signal | Kind | Set by | Effect |
|--------|------|--------|--------|
| `RECORDING` | event | Flow, while the mic is open | The reader declines to speak (a live mic would hear the synthetic voice and Whisper would transcribe it) |
| `SILENCE_READER` | event | Flow, when a recording starts | The reader stops speaking immediately, from a blocked watcher thread |
| `EXIT` | event | The reader's tray **Exit Engine** | `zero_flow.py` hears it and shuts the whole engine down |
| `CLIPBOARD` | mutex | Whoever is using the clipboard | Serialises the reader's copy-the-selection against Flow's paste-and-restore, across processes |

All are best-effort: creating one is free, setting one nobody listens to is a no-op,
and if signalling is unavailable each half behaves as it did before this existed (the
clipboard lock degrades to an in-process lock).
Flow clears `RECORDING` at boot, so a run that was force-killed mid-capture cannot
leave a running reader permanently muted.

---

## 2. The pipeline
Every dictation flows through the same stages (functions named for the refactored code):

```
 [hotkey press]                on_record_hotkey(mode)        — starts a worker thread
        │
        ▼
 1. CAPTURE        process_recording → Capture.callback      — mic @ 16 kHz mono, live meter
        │                                                      (clips < 0.4 s are dropped,
        │                                                      stops itself after 300 s)
        ▼                  ── transcribe_and_inject(), one clip at a time ──
 2. TRANSCRIBE     transcribe_clip()                          — faster-whisper large-v3
        │                                                      GPU float16, CPU int8 fallback
        ▼
 3. REFINE         refine_text(text, mode, context)           — Raw: passthrough
        │                                                      Polish/Translate: local LLM
        ▼
 4. INJECT         inject_text()                              — macros + punctuation, then
        │                                                      clipboard paste at the cursor
        ▼
 [text appears in the focused app]
```

The mode chosen at step 1 is **locked for the whole capture** — it cannot change
mid-recording. Each recording is a **`Capture` object** holding its own mode, audio,
and stop/cancel state, and it is passed down the stages rather than kept in globals.
The next recording can start the moment this one is stopped, while this one's
microphone is still closing; with one shared audio queue and shared "recording" and
"cancel" flags, quick presses used to mix two recordings up (the second wiped the
first's audio, Esc was undone by the next key, a late microphone error stopped the
newer recording). Only the *current* capture may tell the reader the microphone is
closed (`_end_capture`). Steps 2–4 run one clip at a time (`processing_lock`), so clips
are pasted in the order they were spoken.

A recording left running stops by itself after `MAX_RECORDING_SECONDS` (300 s) and is
transcribed as usual.

The clipboard context Polish mode hands the LLM is read *after* the mic closes, not on
the key press: `pyperclip` can block for up to half a second while another app holds
the clipboard, which on the keyboard hook froze the keyboard and before the mic opened
would have cut off the first words.

If any stage after capture raises, the error and traceback go to `flow_debug.log`, the
console says so, and the engine carries on with the next dictation.

---

## 3. Modes & hotkeys
Each is configurable in `.env`; defaults shown. Record modes live in the `MODES`
table in `local_flow.py` as `{lang, op}` pairs.

| Hotkey | Mode | Forced lang | Behaviour |
|--------|------|-------------|-----------|
| `F5` | `en_raw`    | en | Inject English exactly as spoken (no LLM) |
| `F6` | `en_polish` | en | English, then LLM cleans grammar/fillers |
| `F7` | `ar_raw`    | ar | Inject Arabic exactly as spoken (no LLM) |
| `F8` | `ar_polish` | ar | Arabic, then LLM cleans grammar/fillers |
| `F9` | `en2ar`     | en | Transcribe English, LLM translates **→ Arabic** |
| `F10`| `ar2en`     | ar | Transcribe Arabic, LLM translates **→ English** |
| `Shift+F1` | maintenance | — | LLM dedupes/cleans the learned-vocabulary file |
| `Shift+F2` | purge       | — | Clears the debug log + dictation history |
| `Shift+F3` | line fix    | — | Select the current line, fix it via the LLM, paste back |
| `Esc` | cancel | — | Cancels an in-progress recording (Flow does nothing with it when idle; the reader uses it to stop speaking) |

The reader adds `F4` (read the selection) and reuses `Esc` (silence). It registers
them in its own process, so the two halves never contend for a hotkey — `Esc` simply
does the right thing in whichever half is busy.

All record keys are registered with `suppress=True` so they never leak into the
focused app (otherwise `F5` would refresh the browser, etc.). `Esc` is intentionally
**not** suppressed, so it keeps working normally everywhere. The action keys use
`Shift+F1..F3` (whose bare keys aren't record keys) to avoid the modifier/base-key
collision that `Ctrl+F10/F11` had.

Record keys **toggle**: the first press starts a capture, and while recording, pressing
**any** record key **stops** it — it never switches mode. (Mid-recording switching used
to cause accidental translations.) This is not push-to-talk: the `keyboard` library
fires a hotkey on every key-down, auto-repeat included, so holding a record key down
starts and stops the capture over and over.

Heavy handlers (LLM calls, key-sending) are dispatched to a **worker thread** so they
never block the keyboard listener — a blocked listener freezes the whole keyboard.
`_run_async` wraps the `Shift+F1..F3` handlers this way and logs any failure.

---

## 4. Language handling (the bilingual core)
- Every record mode **forces** its language via `MODES[mode]["lang"]` (`en` or `ar`),
  so there is **no detection step** to get wrong — accented English can no longer be
  misheard as Arabic. This is the key design choice.
- `transcribe_clip(language)` passes that language straight to Whisper. (An auto-detect
  path kept "for safety" was removed in 2.0: no mode ever used it.)
- **The Whisper hint (`initial_prompt`) is per language** (`whisper_hint`). Whisper
  reads it as the text that came just before, so its language and style carry over:
  - **Arabic** gets `personas.ARABIC_WHISPER_HINT` — one short, punctuated Arabic
    sentence — plus any Arabic-script vocabulary.
  - **English** gets the Latin-script vocabulary terms.

  One shared list used to prime both. For Arabic that meant a dozen English tech words,
  and on 16 synthetic Arabic clips (fixed decoding, repeated) it measured **~49%
  character errors against ~40%** with the Arabic sentence. Its sentences also came
  out unpunctuated: **1 of 16** ended in `.`/`؟`, against **14 of 16**. The hint is
  sorted, so it no longer changes between runs.

Translate direction is fixed by the mode (`en2ar` / `ar2en`), not detected, so it is
always correct: `to == "en" → TRANSLATE_TO_EN_PROMPT`, else `TRANSLATE_TO_AR_PROMPT`.
Polish picks its prompt the same way: `ARABIC_POLISH_PROMPT` (Modern Standard Arabic)
for `F8`, `STANDARD_SYSTEM_PROMPT` for `F6`.

**Every AI answer is checked against the language the key asked for**
(`checked_ai_output`): an Arabic answer must contain Arabic, an English one English, and
neither may contain Chinese, Japanese or Korean. Otherwise the original words are pasted
and the answer is logged. `qwen2.5:7b` answered the old Arabic Polish prompt in Chinese
5 times out of 5; with this guard the worst case is your unpolished words. Arabic
answers are also stripped of vowel marks and shadda (tanween on alif stays: *جدًا*).

---

## 5. Hardware: GPU with safe CPU fallback (`load_whisper_model`)
1. Find the model on disk (`resolve_whisper_model`) — see *Model files* below.
2. Unless `WHISPER_DEVICE="cpu"`: prepend any pip-installed CUDA DLL folders
   (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) to the DLL search path, load the model
   on `cuda` at `WHISPER_COMPUTE_TYPE` (default `float16`), then **run one real
   inference immediately**. CTranslate2 loads CUDA lazily, so this forces any
   missing-library failure to happen *now* — at boot — where it can be caught.
3. Otherwise, or on failure, load on `cpu` / `int8`.
4. Where it ended up goes into `model_runtime` (e.g. `GPU · int8_float16`), which the
   start-up banner shows, and into the log.
5. **During dictation**, a clip the graphics card fails on — typically out of memory,
   since Whisper, the voice and the AI model share it — is retried on a CPU copy of the
   model (`cpu_fallback_model`, loaded on first need and then kept). `transcribe_clip`
   returns `(None, None)` for a failure, distinct from `("", lang)` for silence, so the
   log no longer blames the microphone for a crash.

Each dictation logs its decode time next to the clip length (`1.21s for 14.2s of
audio`) — the figure `docs/HARDWARE.md` tunes against. Which settings suit which
hardware is decided outside the engine, by `check_hardware.py` and `presets/`: the
engine only reads `.env`.

**Model files.** Both models come from the Hugging Face Hub — Whisper from
`Systran/faster-whisper-<size>`, the voice from `hexgrad/Kokoro-82M` — and both are
read straight from the local cache (`%USERPROFILE%\.cache\huggingface\hub`) whenever
they are there. The Hub is contacted only to download something missing: the first
run, a new `WHISPER_MODEL_NAME`, or a voice picked for the first time.

That is deliberate. Left to themselves, `WhisperModel("large-v3")` and Kokoro ask the
Hub whether each file has changed on **every** start — five requests before a word
was spoken, cached or not. A local-only engine was phoning home on each boot, stalled
at start-up without internet, and drew the Hub's reply to anonymous requests into the
reader's log: *"You are sending unauthenticated requests to the HF Hub. Please set a
HF_TOKEN…"*. A token only raises rate limits; these models are public. Now a normal
start makes no request at all, and the one-time download notice is silenced
(`huggingface_hub` resets its log level on import, so each half sets it afterwards).

---

## 6. Local LLM (`flow_core.py`: `discover_ollama_model`, `query_ollama`)
- The engine picks the LLM in priority order: (1) `OLLAMA_MODEL_NAME` from
  `.env` if set — pins an exact model; (2) otherwise it queries Ollama's `/api/tags` and
  binds to the **first model installed**; (3) otherwise `FALLBACK_LLM` (Ollama unreachable).
  The choice is cached once Ollama has answered (`get_ollama_model`): dictation makes
  it at boot for the banner, the reader only the first time it cleans text with the
  LLM. The fallback is **never** cached — with Ollama down at the first Polish, caching
  it bound the whole session to a model that may not exist, so every request after
  Ollama started got a 404.
- `ask_ollama` sends `instruction + optional context + input` at `temperature 0.2`
  (low, so Polish stays faithful instead of "creatively" translating) and returns the
  answer, or `None` when there is none: unreachable, a non-200 reply (typically 404, a
  model Ollama does not have) or an empty answer — each logged as a warning and shown
  as a toast. Polish, Translate and `Shift+F3` then say **"AI unavailable"** and keep
  your own words; they used to print "Polished" over the unchanged text.
  `query_ollama` is the same call for callers that carry on with the original either
  way (the reader's Smart mode, vocabulary maintenance): it returns the input instead
  of `None`. `warm_up_llm` checks the HTTP status too, so a 404 is not logged as loaded.
- Every request carries **`think: false`**. Reasoning models (Gemma 4) otherwise write
  ~800 hidden tokens before a one-line answer — 5–9 s instead of ~1 s, for the same
  text. Models without reasoning accept and ignore it (checked on qwen2.5 and ALLaM).
- Every request carries **`keep_alive`** (`OLLAMA_KEEP_ALIVE`, default 30 min), and
  `boot()` loads the model on a background thread while Whisper loads
  (`warm_up_llm`). Ollama's own default unloads after 5 idle minutes, and reloading
  made the next Polish wait 3–12 s. Measured: the AI is ready 6.5–8 s after start-up,
  and dictation is ready ≤0.7 s later than without the warm-up. Loading the AI *after*
  Whisper instead left it ready at 10–11 s.
- Every request — and the warm-up, with the **same** options, or Ollama would load the
  model again on the first Polish — carries **`num_ctx`** (`OLLAMA_NUM_CTX`, default
  8,192 tokens). A model file can ask for far more than dictation needs: gemma4-e4b's
  asks for 131,072, which held 3.58 GB of graphics memory against 2.99 GB, with the
  same speed and answers (`tools/bench/bench_llm.py`). 4,096 saved no more, so the
  default leaves room for a five-minute dictation and its answer.
- If the LLM tags a term as `[LEARN: word]`, `_absorb_learned_word` saves it to
  `flow_vocabulary.txt` and strips the tag — **but only if the term appears in what was
  said** (ignoring case and spacing), and never in Chinese, Japanese or Korean script.
  Learned words prime Whisper on every dictation. Before this rule, Arabic Polish had
  taught three misheard words (removed), and a model answering in Chinese tagged a
  Chinese one. Only the English Polish prompt asks for tags at all.
- **Vocabulary maintenance** (`Shift+F1`, `run_memory_maintenance`) hands the whole
  list to the LLM and writes back the terms it returns (`vocabulary_terms`): list
  markers are stripped, and the model's chatter — "Here is the cleaned list:", or any
  line longer than four words — is dropped, since every kept line primes Whisper.
  The previous file is kept as `flow_vocabulary.txt.bak`, and an unchanged result —
  which is also what an unreachable LLM returns — writes nothing.
- Every write to the vocabulary file holds `VOCAB_LOCK`: a Polish can learn a word
  while `Shift+F1` is rewriting the list, and the rewrite keeps it. A learned word is
  always appended on a line of its own, even if the file lost its final newline
  (it once glued "Visa" and the next word into "VisaKokoro").

---

## 7. Anti-hallucination measures
Hallucination originates in Whisper, not the app code. Mitigations in `transcribe_clip`
/ `process_recording`:
- `condition_on_previous_text=False` — stops repetition-loop spirals.
- `beam_size=5` — steadier decoding on short clips.
- `MIN_CLIP_SECONDS = 0.4` — sub-0.4 s captures are discarded (they only hallucinate).
- `vad_filter=True` — Silero VAD hands Whisper only the stretches it judges to be
  speech, so silence and steady noise never reach it (on the benchmark, no clip without
  speech produced any text).
- `TEMPERATURES = (0.0, 0.2, 0.4)` — Whisper's retries when a decode looks unreliable
  stop at 0.4 instead of 1.0, where a retry is close to guessing.
- **Invented endings** (`trim_invented_ending`). Whisper learned from subtitled videos,
  and a short sound after the last word — a breath, a keystroke — passes the VAD as
  "speech"; alone at the end of a clip, it is where Whisper writes "Thank you." or
  "اشتركوا في القناة". Transcription asks for word timings, and a known stock ending
  (`STOCK_ENDINGS`) is dropped from the **very end** only when the audio says it was
  never said: it sits ≥15 dB below the speech before it, or Whisper's own confidence
  in its words is under 0.5 (alone in a clip: below −45 dBFS, or unsure). Levels are
  measured on the clip as recorded, before the volume is normalised. A clearly spoken
  "thank you" passes every test and stays — `tests/test_hallucination.py` pins both
  sides, and every drop is logged with its evidence.

**Measuring it.** `tools/bench/` runs the engine's own transcription (`transcribe_audio`,
the same steps as a dictation) over test clips and scores errors, end punctuation,
invented words and time. Synthetic clips (`make_clips.py`) prove a change does no harm
— on them the filter changed no error rate, kept every real "thank you", and cost
0.02–0.05 s per clip — but they cannot reproduce invented endings, which depend on a
real room and microphone. `record_mine.py` records your own voice for that (kept on
your PC, git-ignored), and `bench_stt.py --no-filter` gives the comparison.

---

## 8. Injection details (`inject_text`)
- **Voice macros** (`personas.VOICE_MACROS`): a leading "new line" / "bullet" /
  "format code" or a trailing "and send" is detected, stripped from the text, and
  turned into the matching keystroke/format (`shift+enter`, `• `, `` `code` ``, `enter`).
  All of this lives in `apply_macros()`, kept separate from `inject_text()` so it can
  be tested without driving the keyboard — see `tests/test_macros.py`.
  Triggers match **whole words only** ("Pointless" is not the "point" macro), and they
  match **through Whisper's punctuation**: Whisper writes what it hears as a sentence,
  so "new line hello … and send" arrives as "New line. Hello … and send." and the
  macros have to see past those marks.
- **Punctuation map**: trailing spoken punctuation ("period", "comma", Arabic
  equivalents) becomes real punctuation. It is matched with Whisper's own closing mark
  removed, so "That is all, period." becomes "That is all."
- **Vocabulary casing**: known terms are re-cased to their canonical form. The term is
  inserted literally (a function replacement, not a `re.sub` template), so a learned
  word containing a backslash cannot break the paste.
- Injection (`paste_text`) saves the clipboard, pastes via `Ctrl+V`, waits 150 ms for
  slow apps to read it, then **restores** the original clipboard — all under the
  cross-process clipboard lock. `Shift+F3` (fix the line) uses the same routine.
- Only **text** survives the save/restore: `pyperclip` cannot hold images or files, so
  an image on the clipboard is gone after a dictation.

---

## 9. The reader (text → speech)
```
 [F4 pressed]                 trigger_read()                — worker thread, never the listener
        │
        ▼
 1. CAPTURE      capture_highlighted_text()                 — synthetic Ctrl+C, clipboard
        │                                                     saved and restored afterwards
        ▼
 2. CLEAN        clean_text_instant()  (regex: URLs,        — or clean_text_smart(), one LLM
        │                markdown, whitespace)                pass, falling back to the regex
        ▼                                                     clean on timeout/long input
 3. SPEAK        stream_audio() → _iter_batches()           — Kokoro-82M, 24 kHz, one batch
        │                       → playback worker             of sentences at a time
        ▼
 [Esc  →  interrupt_audio(): mark queued audio stale; the worker stops the stream]
```

Design notes:
- **The voice model loads lazily** — `torch` stays out of the process until it is
  genuinely needed — but `preload()` warms it on a background thread at startup, so
  the first `F4` does not pay the ~13 s load. Its files come from the local cache
  (`_model_file`, see §5 *Model files*).
- **The log stays readable.** espeak — Kokoro's fallback for words outside its
  dictionary — reports "words count mismatch" whenever it splits a word differently.
  It is harmless and was most of `reader_debug.log`, so the `phonemizer` logger is
  held at ERROR (set after `KPipeline` is built, because creating the espeak backend
  resets it).
- **Text is batched by sentence** (`_iter_batches`). This matters more than it looks:
  Kokoro renders one request into exactly **one** chunk, so handing it a whole
  paragraph means silence until every word is rendered. Splitting on sentence
  boundaries — with a deliberately small *first* batch, since that is the only one
  anybody waits for — cut paragraph latency on CPU from 5.05 s to 1.97 s. The rest
  renders while the first plays.
- **`Esc` cuts in mid-passage**: `interrupt_audio()` bumps a generation counter.
  `stream_audio` stops rendering as soon as it changes, and the playback worker drops
  every chunk from an older generation and aborts the one playing within ~10 ms.
- **Only the playback worker touches `sounddevice`.** Its `play` / `wait` / `stop`
  helpers share one global stream and are not thread-safe: an `sd.stop()` from the
  `Esc` hotkey (or the silence watcher) while the worker sat in `sd.wait()` had both
  threads close the same PortAudio stream. That double free killed the reader with
  `0xC0000005` / `0xC0000374`, so `interrupt_audio()` never calls into audio itself.
- **Pronunciation** fixes live in `personas.PRONUNCIATION_MAP`, deliberately *not* in
  `BASE_VOCABULARY` — that list feeds Whisper's decoder hint and the casing pass,
  where a phonetic spelling would do damage.
- **Smart mode** (tray menu / `READER_SMART_MODE`) sends the capture through
  `flow_core.query_ollama` with `personas.READER_CLEANUP_PROMPT`. It is off by
  default, skipped for long selections, and always falls back to the regex clean —
  the reader never stays silent because the LLM was slow.

---

## 10. Files written at runtime (git-ignored)
| File | Purpose |
|------|---------|
| `flow_capture.wav` | Temporary audio buffer (deleted after each decode) |
| `flow_vocabulary.txt` | Learned proper nouns / tech terms (deduped on write, pruned by `Shift+F1`) |
| `flow_vocabulary.txt.bak` | The list as it was before the last `Shift+F1` rewrite |
| `flow_history.md` | Append-only log of injected text; trimmed after any write that takes it past ~500 KB, at an entry boundary |
| `flow_debug.log` | Dictation diagnostics; auto-rotated at ~1 MB (×2 backups ≈ 3 MB cap) |
| `reader_debug.log` | Reader diagnostics; rotated the same way |
| `flow_crash.log`, `reader_crash.log` | Native crashes (e.g. a segfault in a CUDA library), written by `faulthandler`; normally empty |

Each half logs to its **own** file. That is deliberate: two processes sharing one
`RotatingFileHandler` fight at rollover — on Windows the rename fails outright while
the other process holds the file open, and the log then grows forever, defeating the
rotation. `Shift+F2` clears the dictation log and history; the reader's log rotates
on its own (it writes a handful of lines per read).

**None of these grow without bound:** both debug logs rotate, history is trimmed as it
is written, and `Shift+F2` clears the dictation pair on demand. The debug logs are the
first place to look when something misbehaves — every transcription records `mode=…`
and `lang=…`, and re-decodes / skips / fallbacks / failures are all logged, dictation
in `flow_debug.log` and the reader in `reader_debug.log`. An uncaught exception on any
thread is logged there too (`sys.excepthook`, `threading.excepthook`, set up by
`init_logging`), and a fatal one also shows a message box — a hidden engine's console
is never seen.

---

## 10a. Processes: one copy, a supervised reader, nothing left behind
- **One copy at a time.** Each start claims its role with a named mutex
  (`flow_signals.claim_single_instance`): `zero_flow.py` claims both "dictation" and
  "reader", `local_flow.py` "dictation", a standalone reader "reader". A second copy
  says it is already running and closes — two engines used to paste every dictation
  twice. Windows drops a claim when its process ends, however it ends.
- **The reader is supervised.** It exits with code 1 when it crashes (it used to exit
  0, which looked like a clean exit). `watch_reader` restarts it after 2, 4 and 8 s,
  then gives up and says so; a reader that ran for a minute earns fresh tries. Exit
  from the tray, a closed console (`0xC000013A`) and the engine's own `shutdown()` are
  not crashes.
- **The reader dies with the engine.** `spawn_reader` puts it in a Windows Job Object
  with *kill on close* (`flow_signals.bind_child_to_this_process`). Only the engine
  holds the job's handle, so when the engine ends — even by a crash or End task, when
  none of its clean-up code runs — Windows ends the reader too.
- **A standalone reader's Exit** quits only itself. The exit signal is shared, and it
  used to shut down a full engine running alongside.
- **Launchers** pass `silent` from the `.vbs` files: started hidden, a launcher never
  waits for a key (each exit used to leave an invisible `cmd.exe` behind); started
  visible, it pauses only after an error, so the message can be read.

---

## 11. Known gaps
- **Console interleaving.** Dictation redraws a live level meter with `\r` while
  recording. The mic interlock stops reading and recording overlapping, so the two
  rarely print at once, but nothing enforces it.
- **"point" is an ambiguous trigger.** The bullet macro matches whole words only, so
  "Pointless" is safe, but a sentence that genuinely begins with the word "Point" still
  becomes a bullet. Remove it from `VOICE_MACROS["bullet"]` if that bites. (The Arabic
  equivalents were fixed: bare "نقطة" and "كود" started everyday sentences, so bullets
  now need "قائمة" and code "تنسيق كود".)
- **The reader speaks English only.** Kokoro has no Arabic voice, so highlighted Arabic
  is not read aloud properly.
- **Images on the clipboard are lost** by dictation, `F4` and `Shift+F3` (see §8).

Fixed since they were listed here: the **clipboard race** (`flow_signals.clipboard_lock()`
is a named Windows mutex, so it serialises the two halves across the process boundary
as well as within one), and the **orphaned reader** (see §10a).

---

## 12. The CUDA constraint (read before touching device selection)
**Whisper and Kokoro cannot both use CUDA in one process. The result is a segfault,
not an exception — nothing can catch it and no fallback runs.**

- `torch 2.5.1+cu121` bundles cuDNN **9.1** in `torch/lib`.
- CTranslate2 4.8 (behind faster-whisper) uses the pip `nvidia-cudnn-cu12` **9.23**.
- Windows loads exactly **one DLL per base name per process**. Whichever initialises
  CUDA second gets the other's `cudnn64_9.dll`, its symbols don't match, and the
  process dies. Verified in **both** load orders: Whisper-then-Kokoro fails with
  `Could not load symbol cudnnGetLibConfig` (error 127), Kokoro-then-Whisper segfaults.

**This is why `zero_flow.py` is a supervisor rather than a merge.** Two processes
have two DLL namespaces, so each model loads the CUDA libraries it was built against
and neither treads on the other. Anyone hosting both halves in one process again has to
run the voice on the CPU (`READER_DEVICE=cpu`) — which is what the merged build did,
and these are the numbers that cost, measured warm:

| | short sentence | paragraph | throughput |
|---|---|---|---|
| GPU | 0.07 s | 0.22 s | 52-82x realtime |
| CPU, whole passage in one call | 0.82 s | **5.05 s** | 3.6-5.2x realtime |
| CPU, sentence-batched (current) | 0.82 s | **1.97 s** | same |

Both devices stay ahead of playback once speech starts; what differs is the wait
before the first word. The supervisor layout gets the 0.22 s figure back.

**CTranslate2 would import torch, too.** Its `converters` package — for turning other
model formats into its own, never used here — tries `import torch, transformers` on
import. Both are installed (the reader's voice needs them), so the attempt succeeds and
costs ~6 s on every start, loading torch into the dictation process for nothing.
`local_flow.py` marks the two as unavailable for that one import (CTranslate2 already
treats them as optional) and removes the marker straight after. Measured: engine ready
in 5.0–5.3 s instead of ~10.2 s, test suite ~2 s instead of ~8 s, and no torch in the
dictation process at all. `tests/test_startup.py` fails if a CTranslate2 upgrade
undoes it. If CTranslate2 ever *needs* torch, the engine fails at start-up with an
ImportError — loudly, not subtly — and the fix is to remove the skip.

**A second, related trap: import order.** `win11toast` (reached through `engine_ui`)
loads WinRT native libraries. If that happens *before* faster-whisper claims its CUDA
DLLs, CTranslate2 segfaults when it later loads the model on the GPU. Two defences:

1. `engine_ui.show_toast` imports `win11toast` **lazily**, inside the worker thread,
   so simply importing the UI module is harmless.
2. `zero_flow.py` imports `local_flow` **first**, before anything that reaches
   `engine_ui`.

Keep both. If you reorder these imports, re-test by launching `zero_flow.py` and
confirming `flow_debug.log` still says `Whisper model active on CUDA (float16)`.
