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
| `tests/`        | Standard-library unit tests for the pure text logic (`python -m unittest discover -s tests`) |

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

The one resource they would fight over — the microphone — is coordinated with Windows
named events in `flow_signals.py`. Named events work within a single process as well
as across two, so the merged engine uses exactly the same code path:

| Signal | Set by | Effect |
|--------|--------|--------|
| `RECORDING` | Flow, while the mic is open | The reader declines to speak (a live mic would hear the synthetic voice and Whisper would transcribe it) |
| `SILENCE_READER` | Flow, when a recording starts | The reader stops speaking immediately, from a blocked watcher thread |

Both are best-effort: creating an event is free, setting one nobody listens to is a
no-op, and if signalling is unavailable each half behaves exactly as it did before.
Flow clears `RECORDING` at boot, so a run that was force-killed mid-capture cannot
leave a running reader permanently muted.

---

## 2. The pipeline
Every dictation flows through the same stages (functions named for the refactored code):

```
 [hotkey press]                on_record_hotkey(mode)        — starts a worker thread
        │
        ▼
 1. CAPTURE        process_recording → audio_callback        — mic @ 16 kHz mono, live meter
        │                                                      (clips < 0.4 s are dropped)
        ▼
 2. TRANSCRIBE     transcribe_clip()                          — faster-whisper large-v3
        │                                                      GPU float16, CPU int8 fallback
        ▼
 3. REFINE         refine_text(text, lang)                    — Raw/English: passthrough
        │                                                      Polish/Translate: local LLM
        ▼
 4. INJECT         inject_text()                              — macros + punctuation, then
        │                                                      clipboard paste at the cursor
        ▼
 [text appears in the focused app]
```

The mode chosen at step 1 (`active_mode`) is **locked for the whole capture** — it
cannot change mid-recording.

---

## 3. Modes & hotkeys
Each is configurable in `.env`; defaults shown.

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
| `Esc` | cancel | — | Cancels an in-progress recording **only** (does nothing when idle) |

The reader adds `F4` (read the selection) and reuses `Esc` (silence). It registers
them in its own process, so the two halves never contend for a hotkey — `Esc` simply
does the right thing in whichever half is busy.

All record keys are registered with `suppress=True` so they never leak into the
focused app (otherwise `F5` would refresh the browser, etc.). `Esc` is intentionally
**not** suppressed, so it keeps working normally everywhere. The action keys use
`Shift+F1..F3` (whose bare keys aren't record keys) to avoid the modifier/base-key
collision that `Ctrl+F10/F11` had.

While recording, pressing **any** record key **stops** the capture — it never switches
mode. (Mid-recording switching used to cause accidental translations.)

Heavy handlers (LLM calls, key-sending) are dispatched to a **worker thread** so they
never block the keyboard listener — a blocked listener freezes the whole keyboard.

---

## 4. Language handling (the bilingual core)
- Every record mode **forces** its language via `MODES[mode]["lang"]` (`en` or `ar`),
  so there is **no detection step** to get wrong — accented English can no longer be
  misheard as Arabic. This is the key design choice.
- `transcribe_clip(force_lang)` passes that language straight to Whisper.
- It still keeps an auto-detect path (`force_lang=None`): if Whisper ever drifts to a
  language outside `SUPPORTED_LANGS` (`ar`/`en`), it re-decodes as the closer of the two.
  No current mode uses this path, but it's there for safety.
- The Whisper hint (`initial_prompt`) is **only the vocabulary term list** — never an
  English sentence, which would bias the decoder toward English.

Translate direction is fixed by the mode (`en2ar` / `ar2en`), not detected, so it is
always correct: `to == "en" → TRANSLATE_TO_EN_PROMPT`, else `TRANSLATE_TO_AR_PROMPT`.

---

## 5. Hardware: GPU with safe CPU fallback (`load_whisper_model`)
1. Prepend any pip-installed CUDA DLL folders (`nvidia-cublas-cu12`,
   `nvidia-cudnn-cu12`) to the DLL search path.
2. Load the model on `cuda` / `float16`, then **run one real inference immediately**.
   CTranslate2 loads CUDA lazily, so this forces any missing-library failure to happen
   *now* — at boot — where it can be caught.
3. On failure, fall back to `cpu` / `int8`. The active device is written to the log.

---

## 6. Local LLM (`discover_ollama_model`, `query_ollama`)
- At boot the engine picks the LLM in priority order: (1) `OLLAMA_MODEL_NAME` from
  `.env` if set — pins an exact model; (2) otherwise it queries Ollama's `/api/tags` and
  binds to the **first model it is serving**; (3) otherwise `FALLBACK_LLM` (Ollama unreachable).
- `query_ollama` sends `instruction + optional context + input` at `temperature 0.2`
  (low, so Polish stays faithful instead of "creatively" translating). On any error it
  returns the original text unchanged, so a dead LLM never loses your dictation.
- If the LLM tags a term as `[LEARN: word]`, `_absorb_learned_word` saves it to
  `flow_vocabulary.txt` and strips the tag.

---

## 7. Anti-hallucination measures
Hallucination originates in Whisper, not the app code. Mitigations in `transcribe_clip`
/ `process_recording`:
- `condition_on_previous_text=False` — stops repetition-loop spirals.
- `beam_size=5` — steadier decoding on short clips.
- `MIN_CLIP_SECONDS = 0.4` — sub-0.4 s captures are discarded (they only hallucinate).
- the `ar/en` re-decode (section 4) — prevents wrong-language gibberish.

---

## 8. Injection details (`inject_text`)
- **Voice macros** (`personas.VOICE_MACROS`): a leading "new line" / "bullet" /
  "format code" or a trailing "and send" is detected, stripped from the text, and
  turned into the matching keystroke/format (`shift+enter`, `• `, `` `code` ``, `enter`).
  All of this lives in `apply_macros()`, kept separate from `inject_text()` so it can
  be tested without driving the keyboard — see `tests/test_macros.py`.
- **Punctuation map**: trailing spoken punctuation ("period", "comma", Arabic
  equivalents) becomes real punctuation.
- **Vocabulary casing**: known terms are re-cased to their canonical form.
- Injection is done by saving the clipboard, pasting via `Ctrl+V`, then **restoring**
  the original clipboard.

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
 [Esc  →  interrupt_audio(): sd.stop() + flush the queue]
```

Design notes:
- **The voice model loads lazily** — `torch` stays out of the process until it is
  genuinely needed — but `preload()` warms it on a background thread at startup, so
  the first `F4` does not pay the ~13 s load.
- **Text is batched by sentence** (`_iter_batches`). This matters more than it looks:
  Kokoro renders one request into exactly **one** chunk, so handing it a whole
  paragraph means silence until every word is rendered. Splitting on sentence
  boundaries — with a deliberately small *first* batch, since that is the only one
  anybody waits for — cut paragraph latency on CPU from 5.05 s to 1.97 s. The rest
  renders while the first plays.
- **`Esc` cuts in mid-passage**: `stream_audio` re-checks `stop_playback` between
  batches and between chunks, so it stops without finishing the render.
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
| `flow_history.md` | Append-only log of injected text; auto-trimmed at boot past ~500 KB |
| `flow_debug.log` | Dictation diagnostics; auto-rotated at ~1 MB (×2 backups ≈ 3 MB cap) |
| `reader_debug.log` | Reader diagnostics; rotated the same way |

Each half logs to its **own** file. That is deliberate: two processes sharing one
`RotatingFileHandler` fight at rollover — on Windows the rename fails outright while
the other process holds the file open, and the log then grows forever, defeating the
rotation. `Shift+F2` clears the dictation log and history; the reader's log rotates
on its own (it writes a handful of lines per read).

**None of these grow without bound:** both debug logs rotate, history is trimmed at boot,
and `Shift+F2` clears the dictation pair on demand. The debug log is the first place to look when
something misbehaves — every transcription records `mode=…` and `lang=…`, and
re-decodes / skips / fallbacks are all logged. Both halves write to the same log.

---

## 11. Known gaps
- **The child can be orphaned.** If the parent is force-killed (Task Manager, not the
  tray), the reader survives as a tray app. Its own Exit still works. A Windows Job
  Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` would close this properly; worth
  adding only if orphans actually turn up in practice.
- **Console interleaving.** Dictation redraws a live level meter with `
` while
  recording. The mic interlock stops reading and recording overlapping, so the two
  rarely print at once, but nothing enforces it.

The clipboard race listed here previously is **fixed**: `flow_signals.clipboard_lock()`
is a named Windows mutex, so it serialises the two halves across the process boundary
as well as within one.

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
and neither treads on the other. `voice_engine.force_cpu()` survives as the guard for
anyone who tries hosting both halves in one process again — it is what the merged
build had to call, and these are the numbers that cost, measured warm:

| | short sentence | paragraph | throughput |
|---|---|---|---|
| GPU | 0.07 s | 0.22 s | 52-82x realtime |
| CPU, whole passage in one call | 0.82 s | **5.05 s** | 3.6-5.2x realtime |
| CPU, sentence-batched (current) | 0.82 s | **1.97 s** | same |

Both devices stay ahead of playback once speech starts; what differs is the wait
before the first word. The supervisor layout gets the 0.22 s figure back.

**A second, related trap: import order.** `win11toast` (reached through `engine_ui`)
loads WinRT native libraries. If that happens *before* faster-whisper claims its CUDA
DLLs, CTranslate2 segfaults when it later loads the model on the GPU. Two defences:

1. `engine_ui.show_toast` imports `win11toast` **lazily**, inside the worker thread,
   so simply importing the UI module is harmless.
2. `zero_flow.py` imports `local_flow` **first**, before anything that reaches
   `engine_ui`.

Keep both. If you reorder these imports, re-test by launching `zero_flow.py` and
confirming `flow_debug.log` still says `Whisper model active on CUDA (float16)`.
