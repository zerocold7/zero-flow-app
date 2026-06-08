# Changelog

All notable work on the **Zero- Flow Engine**. Newest first.

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
