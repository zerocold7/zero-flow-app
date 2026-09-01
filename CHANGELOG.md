# Changelog

All notable work on the **Zero- Flow Engine**. Newest first.

---

## [1.1.0] — 2026-09-01 — The reader: text → speech

The engine gained its second half. Highlight text anywhere, press `F4`, and a local
**Kokoro-82M** voice reads it aloud. Dictation is unchanged in behaviour.

### ✨ Added
- **`reader/`** — the text-to-speech half, run with `Launch_Reader.bat` /
  `Launch_Reader_Silent.vbs` / `python -m reader`. `F4` reads the selection, `Esc`
  silences it, and the tray menu switches voice, smart cleaning and suspend.
- **Lazy voice-model loading** — Kokoro (and `torch` with it) is imported on the first
  read, not at startup, so the reader launches instantly.
- **Chunked playback** — speech starts before the passage finishes synthesising and
  can be cut off mid-sentence.
- **`READER_*` settings** in `.env` (hotkey, voice, smart mode, limits) — see
  CONFIGURATION.md §10.
- **`Launch_All.bat` / `Launch_All_Silent.vbs`** — start both halves at once. Either
  half still runs perfectly well on its own.
- **`flow_signals.py`** — Windows named events that coordinate the two processes over
  the microphone: starting a dictation silences the reader, and the reader refuses to
  speak while the mic is open, so Whisper can never transcribe the synthetic voice.
  Best-effort — if signalling is unavailable both halves behave as they did before,
  and Flow clears the flag at boot so a force-killed run cannot leave the reader mute.

### 🔧 Changed
- **New `flow_core.py`** — paths, `.env` config, the rotating debug log, the learned
  vocabulary and the Ollama client moved out of `local_flow.py` into one shared
  module. Both halves now use **one** LLM client, **one** vocabulary and **one** log.
- **The LLM name is resolved lazily and cached**, instead of at dictation startup.
- **The reader honours your `.env`** — it previously hardcoded `qwen2.5:7b`, the
  Ollama URL, and a 3-second timeout that made its LLM pass fail silently almost every
  time. It now uses the engine's model discovery, `OLLAMA_MODEL_NAME` pin and fallback.
- **The reader restores your clipboard** after reading a selection, matching what the
  dictation half already did.
- **`F4` is suppressed** while the reader runs, so it never leaks into the focused app
  (the same rule the dictation record keys follow).
- **`requirements.txt`** — added `kokoro`; corrected the stale `soundfile` and
  `win11toast` pins to the versions actually in use.
- **Each half logs to its own file** (`flow_debug.log`, `reader_debug.log`). Two
  processes sharing one `RotatingFileHandler` cannot roll over on Windows — the
  rename fails while the other holds the file open and the log grows unbounded.
- **`Launch_*_Silent.vbs` resolve their own folder** instead of relying on the
  working directory.

### 🗑️ Removed
- The reader's duplicate Ollama client, duplicate console theme, and hardcoded
  "RTX 4070 / qwen2.5:7b" banner (it reported those regardless of the real hardware).

---

## [1.0.0] — 2026-06-08 — First complete, documented release

A local, private, bilingual (Arabic / English) voice-dictation and text-injection
engine for Windows 11. Hold a hotkey, speak, and the text appears in whatever app has
focus. Everything runs on-device by default.

### ✨ Features
- **Local speech-to-text** with `faster-whisper large-v3`.
- **GPU with automatic CPU fallback** — runs on NVIDIA CUDA (`float16`); if the CUDA
  libraries are missing it falls back to CPU (`int8`), verified with a real inference
  at boot so failures surface immediately instead of mid-dictation.
- **Six language-forced record modes** (the key forces the language, so it can never
  misdetect):
  - `F5` English · raw  `F6` English · polish
  - `F7` Arabic · raw   `F8` Arabic · polish
  - `F9` Translate English → Arabic   `F10` Translate Arabic → English
- **Action keys:** `Shift+F1` vocabulary maintenance · `Shift+F2` clear logs/history ·
  `Shift+F3` fix current line · `Esc` cancel recording.
- **Dynamic local LLM** via Ollama — auto-discovers the served model (no hardcoding);
  powers Polish, Translate, line-fix and maintenance.
- **Self-evolving vocabulary** (`[LEARN: …]`), **voice macros** ("new line", "bullet",
  "format code", "and send"), and a **punctuation map** — all bilingual.
- **Safe injection** via clipboard paste that restores your original clipboard.
- **Background UX:** system-tray icon, console-window icon, audio chimes, Windows toasts.

### 🛠️ Reliability & fixes
- **CUDA:** install/load `nvidia-cublas-cu12` + `nvidia-cudnn-cu12`, with clean CPU fallback.
- **Anti-hallucination:** `condition_on_previous_text=False`, `beam_size=5`, drop clips
  < 0.4 s, and re-decode to Arabic/English if Whisper drifts to a third language.
- **Bilingual correctness:** language is forced per key (no misdetection); translation
  direction is fixed by the key (always correct).
- **Hotkey stability:** `suppress=True` (no key leaks into apps), heavy handlers run off
  the keyboard-listener thread (no keyboard freezes), no mid-recording mode switching,
  and action keys on `Shift+F1..F3` to avoid modifier/base-key collisions.
- **`Esc`** only cancels a recording (it no longer sends Ctrl+Z into the focused app).
- **Bounded files:** debug log auto-rotates (~3 MB cap), history trimmed at boot,
  `Shift+F2` purges both on demand.
- **Notifications:** silenced the `win11toast` console leak.

### 🧹 Codebase & docs
- Refactored `local_flow.py` into a clean `main()` with small, named stages; a single
  `MODES` table is the source of truth for the record modes.
- Full docs: **README.md** (overview/setup), **CONFIGURATION.md** (every tweak,
  including changing the languages and swapping the LLM provider + API keys), and
  **ARCHITECTURE.md** (internals).

### Personal/runtime data (never committed)
`flow_vocabulary.txt`, `flow_history.md`, `flow_debug.log*`, `flow_capture.wav`, and
`.env` are git-ignored.
