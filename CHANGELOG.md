# Changelog

All notable work on the **Zero- Flow Engine**. Newest first.

---

## [1.4.0] — 2026-09-19 — Every kind of PC, explained and tuned

### ✨ Added
- **`check_hardware.py`** — detects the graphics card (exact memory, from the registry
  and `nvidia-smi`; WMI stops at 4 GB), RAM and CPU; picks one of four tiers; prints the
  settings to use and what is still missing (packages, the torch build, Ollama and its
  model, model downloads). `--apply` merges the settings into `.env`, keeping
  everything else and saving the old file as `.env.bak`. Standard library only, so it
  runs straight after cloning; it inspects the engine's `venv`, not the Python that
  runs it.
- **`presets/`** — `nvidia-desktop`, `nvidia-laptop`, `cpu-only`, `amd-intel-gpu`: the
  model and device settings for each tier, usable on their own as a `.env`.
- **`WHISPER_DEVICE`** (`auto` | `cpu`) — skip the GPU attempt on machines without an
  NVIDIA card, or to leave the card to the AI model.
- **`WHISPER_COMPUTE_TYPE`** — GPU precision. `int8_float16` halves the speech model's
  graphics memory: large-v3 **3.9 GB → 2.0 GB**, 0.9 s → 1.1 s per 14 s clip, measured
  on an RTX 4070 with no loss on the test clip.
- **Decode timing** — the console (`📝 Raw (1.2s): …`) and `flow_debug.log`
  (`1.21s for 14.2s of audio`) show how long each clip took, and the banner shows
  where the model loaded (`Whisper large-v3 · GPU · float16`) instead of the old
  fixed "NVIDIA / CPU ALLOCATED" placeholder.
- **Docs:** a new README front page (what it is, how it works, which PC you need, a
  docs index), **docs/INSTALL.md** (one path, with the per-hardware fork),
  **docs/HARDWARE.md** (the four tiers, measured numbers, every tuning setting, a
  symptom → fix table, laptop heat), **docs/FAQ.md**, and Arabic versions of the
  install and hardware guides.
- 19 tests for the tiers, the presets, the `.env` merge and the device setting (80 in all).

### 📝 Docs
- CONFIGURATION.md's Whisper table overstated large-v3's memory (it said 5–6 GB; it
  measures 3.9 GB) and called `distil-large-v3` "English-leaning" — it is English
  only, so it cannot serve the Arabic keys.

---

## [1.3.2] — 2026-09-19 — The reader stops crashing; macros work on real speech

### 🐛 Fixed
- **The reader crashed on `Esc`, on a second `F4`, or when dictation started
  mid-read** (`0xC0000005` / `0xC0000374` in `flow_debug.log`). `interrupt_audio()`
  called `sd.stop()` from another thread while the playback worker sat in `sd.wait()`,
  and both closed the same PortAudio stream — a double free. Reproduced outside the
  app (2 of 6 stress runs segfaulted). The playback worker is now the only thread
  that touches `sounddevice`; `interrupt_audio()` just marks queued audio stale, and
  the worker aborts within ~10 ms. The same stress on the fix: 8 of 8 runs clean.
  The worker also survives a failed chunk instead of dying and leaving the reader mute.
- **Voice macros and spoken punctuation almost never fired.** Whisper punctuates what
  it hears — most real transcripts end in `.` or `?` — so "… and send." never matched
  `endswith("and send")`, "That is all, period." kept its "period", and "New line.
  Hello" pasted ". Hello". Macros now match through Whisper's punctuation.
- **Macro triggers matched inside words:** "Pointless" pasted as "• less",
  "Bulletproof" as "• proof", "New lines of code" as a newline plus "s of code".
  Triggers are whole words now.
- **A learned word containing a backslash lost every dictation** it appeared in: it
  was used as a `re.sub` template and raised "bad escape".
- **Starting a dictation while the previous one was still transcribing** could polish
  or translate the earlier clip with the new mode, and paste the two out of order.
  The mode now travels with its clip, and clips are processed one at a time.
- **A failure after capture killed the worker silently** (a clipboard held by another
  app, say): nothing in the log, and the title stuck on `DECODING`. Now logged, and
  the engine carries on. The same goes for the `Shift+F1..F3` action keys.
- **`Shift+F2` could freeze the whole engine**: an error while truncating the log
  left the log handler's lock held, blocking every later log call.
- **`Shift+F3` skipped the clipboard lock** the rest of the engine uses, restored the
  clipboard after 30 ms (slow apps then paste the *old* contents), and could mistake a
  failed copy for the line when the clipboard ended in a newline.
- **Closing the console window was logged as a reader crash** (`0xC000013A`, 13 times
  in the current log). It is the user stopping the engine, and is logged as such.
- **A mic that will not open** (unplugged, blocked in privacy settings) now says so in
  the console and resets the tray, instead of failing silently in the log.
- **Ollama errors were invisible.** A wrong model name (HTTP 404) returned the text
  unpolished with no toast and no log line. Both are now reported.
- **Every start contacted Hugging Face** — four requests from the reader, one from
  dictation — even with every model already on disk. That was the source of *"You are
  sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN…"* in
  `reader_debug.log` (the Hub's reply to an anonymous request), stalled start-up with
  no internet, and contradicted the README's "nothing leaves your machine". Both
  halves now read their models straight from the local cache and download only what
  is missing, once. No token is needed: the models are public. Verified: zero
  requests on a normal start, and a clean start with the Hub forced offline.
- The voice module's attempt to quiet `huggingface_hub` never worked — the library
  resets its log level when it is first imported, which happened later. The level is
  now set after the import.
- **`reader_debug.log` was mostly noise:** 137 of its 167 warnings were espeak's
  harmless "words count mismatch". Held at ERROR now, so real problems stand out.

### 🗑️ Removed
- `docs/Zero-Flow-Laptop-Setup-Guide.pdf` — a byte-identical copy of
  `Zero-Flow-Setup-Guide.pdf` that nothing links to any more.
- `voice_engine.force_cpu()` — a guard for the single-process layout that 1.3.0
  retired; nothing called it, and `READER_DEVICE=cpu` does the same job.
- The unused `flow_core.LOG_COMPONENTS` constant and the unused `mode_shift` chime.

### 🔧 Changed
- **`Shift+F1` keeps a backup** (`flow_vocabulary.txt.bak`) before letting the LLM
  rewrite the vocabulary, strips the `- ` / `1. ` list markers models like to add, and
  no longer reports success (or rewrites the file) when nothing changed — which is
  also what an unreachable LLM looks like.

### ✨ Added
- 23 tests (61 in all): Whisper-punctuated macros, whole-word triggers, the backslash
  case, playback thread ownership and interrupts, and vocabulary maintenance. 19 of
  them fail against 1.3.1.

### 📝 Docs
A full pass over every document against the code as it now stands.
- **The beginner guides taught push-to-talk; the engine toggles.** "Hold F5, speak,
  release" starts *and* stops a recording on the key's auto-repeat. Both guides — and
  the README, which never said — now read: press once, speak, press again.
- **The English guide's GPU edit deleted the voice.** "Delete the last two lines of
  `requirements.txt`" removed `kokoro` since the reader was added, and left the NVIDIA
  lines in. It now names the two `nvidia-` lines.
- **The Arabic guide installed no voice at all:** its hand-copied `pip install` list
  predated the reader and pinned an old `soundfile`. It now reads `requirements.txt`
  itself and skips only the `nvidia-` lines, so it cannot drift again.
- Both guides pick the LLM with `OLLAMA_MODEL_NAME` rather than `FALLBACK_LLM` (which
  only applies when Ollama is unreachable), set `READER_DEVICE="cpu"`, start with
  `Launch_Zero.bat`, say what "ready" actually looks like (the console never printed
  the log line they quoted), stop from the tray's **Exit Engine** rather than Task
  Manager, list the spoken commands, and troubleshoot `F4`, a wrong model name and
  the debug logs.
- **The printable PDF and the Arabic Word file are regenerated** from the current
  guides. The PDF predated the reader and still installed into Documents, the
  OneDrive trap the guide warns about.
- **CONFIGURATION.md's "other LLM provider" recipe could not work:** it pointed at
  `local_flow.py` (the client is in `flow_core.py`) and at an `OLLAMA_MODEL` variable
  and a `main()` step that no longer exist. Rewritten against the current code, with
  a current Claude model id; both snippets are executed against a mock server.
- README: a voice-macro and spoken-punctuation summary, the CUDA `torch` step for the
  GPU voice, the reader's warm-up, a "when something goes wrong" section, and no more
  "merged" layout or shared debug log — both gone since 1.3.0.
- ARCHITECTURE.md: all four cross-process signals (it listed two), the per-clip mode
  and processing lock, failure logging, `paste_text`, vocabulary maintenance and its
  backup, and new known gaps (the ambiguous "point" trigger, images on the clipboard).
- `.env.example` no longer claims `READER_DEVICE` is ignored by `Launch_Zero.bat`,
  and nothing calls that launcher "single process" any more — both stopped being true
  in 1.3.0. `engine_ui.py` gains the module docstring every other module has.

---

## [1.3.1] — 2026-09-01 — Correctness pass

### 🐛 Fixed
- **Pronunciation fixes were case-sensitive.** `aqeeq` was corrected while `Aqeeq`
  went through untouched. Matching is now case-insensitive and anchored to word
  boundaries, so `Nasu` is still fixed but `Nasuverse` is left alone.
- **Footnote markers were read aloud as numbers.** The clean-up stripped `[` and `]`
  but kept the digits, so `[1]` became a spoken "one". Reference markers are now
  dropped whole, and the space they used to strand before punctuation goes with them.
- **`Launch_Silent.vbs` depended on the working directory**, so it failed whenever it
  was started from anywhere but its own folder (a shortcut, Startup, Task Scheduler).
- **A CPU-only torch install failed silently.** `requirements.txt` cannot express the
  `+cu121` index, so a plain `pip install -r` can fetch the CPU wheel and halve speech
  speed with no error anywhere. The engine now logs exactly that, with the fix.

### ✨ Added
- **`tests/`** — 38 standard-library unit tests over the text logic that breaks
  quietly: voice macros and spoken punctuation, sentence batching, reader clean-up,
  and `[LEARN: …]` vocabulary absorption. `python -m unittest discover -s tests`.
- `local_flow.apply_macros()`, split out of `inject_text()` so that logic is testable
  without a keyboard or a clipboard.

### 📝 Docs
- The beginner setup guides (English and Arabic) now cover the reader, `F4`, and
  `Launch_Zero.bat`, and are honest about the wait on a laptop with no GPU.
- The two setup **PDFs** are stale — they predate the reader — and are flagged as such
  in the README. They are generated artifacts and need rebuilding from source.

---

## [1.3.0] — 2026-09-01 — One window and the GPU, at the same time

`Launch_Zero.bat` no longer trades speech speed for a single window. It gets both.

### 🔧 Changed
- **`zero_flow.py` is now a supervisor, not a merge.** It runs dictation in its own
  process and launches the reader as a **child process** started without
  `CREATE_NEW_CONSOLE`, so Windows hands the child the parent's console: its output
  appears in the same window and the pair looks like one program. The child owns the
  single tray icon, since every control in that menu toggles reader state.
- **The voice model is back on the GPU under `Launch_Zero.bat`** — two processes mean
  two DLL namespaces, so the cuDNN collision that forced CPU simply cannot happen.
  Time to first spoken word: **~2.0 s → ~0.2 s**.
- **A crash in one half no longer takes the other down.** The parent logs and reports
  a child that dies; dictation keeps working without it.
- `READER_DEVICE` is honoured under every launcher again.

### ✨ Added
- `flow_signals.request_exit()` / `wait_for_exit()` — the tray belongs to the child,
  so "Exit Engine" has to reach the parent.
- `reader/app.py` gains a child mode (`ZEROFLOW_CHILD=1`): no banner, no `cls`, and
  the console title is left to the parent so the two do not overwrite each other.

### 🐛 Fixed
- **The clipboard race is closed.** `flow_core.CLIPBOARD_LOCK` was a `threading.RLock`
  and so only ever bound callers inside one process. It is now
  `flow_signals.clipboard_lock()`, a named Windows mutex that serialises the reader's
  capture against the dictation half's paste-and-restore across processes too.
  ARCHITECTURE.md §11 listed this as an open hazard; it no longer is.

---

## [1.2.1] — 2026-09-01 — Faster reading on CPU

The merged engine's reading was noticeably slower to start, and the 1.2.0 notes
understated it. Corrected, with measurements.

### 🐛 Fixed
- **Speech now starts after the first sentence, not the whole passage.** Kokoro
  renders a request into exactly one chunk, so the previous "chunked playback" was a
  single chunk: nothing played until the entire selection had been synthesised.
  `stream_audio` now feeds the model sentence-aligned batches with a deliberately
  small first one. Time to first spoken word for a paragraph on CPU: **5.05 s → 1.97 s**.
- **The voice model is warmed at startup** on a background thread, so the first read
  of a session no longer pays the ~13 s model load.

### 📝 Corrected
1.2.0 claimed CPU synthesis cost "nothing you can hear". That was throughput
(3.6-5.2x realtime), not latency, and latency is what you feel. Measured
time-to-first-word: **GPU 0.22 s, CPU 1.97 s** for a paragraph. The docs now carry the
real numbers, and `Launch_All.bat` remains the way to keep the voice on the GPU.

### ✨ Added
- `READER_FIRST_BATCH_CHARS` (120) and `READER_BATCH_CHARS` (300).

---

## [1.2.0] — 2026-09-01 — One process, one window

`Launch_Zero.bat` runs both halves in a single process: one console, one tray icon,
one log, one clipboard lock. Both halves still run standalone, and `Launch_All.bat`
still runs them as two processes.

### ✨ Added
- **`zero_flow.py`** — the merged engine. Hosts dictation and the reader together,
  with a combined banner, a single tray menu and a single exit.
- **`Launch_Zero.bat` / `Launch_Zero_Silent.vbs`**.
- **`READER_DEVICE`** (`auto` / `cpu` / `cuda`) for the voice model.
- **`flow_core.CLIPBOARD_LOCK`**, held across the reader's capture and the dictation
  half's paste-and-restore, closing the clipboard race in the merged engine.

### 🔧 Changed
- `local_flow.main()` split into `boot()` + `register_hotkeys()`, and the reader's
  logic moved from `reader/__main__.py` into `reader/app.py`, so the merged entry
  point can compose both halves instead of duplicating them.
- One log per process: the first caller names it, so the merged engine puts both
  halves back into `flow_debug.log`.

### 🐛 Fixed
- **`engine_ui` no longer imports `win11toast` at module scope.** It pulls in WinRT
  native libraries, and if that happened before faster-whisper claimed its CUDA DLLs,
  CTranslate2 **segfaulted the process** when loading the model on the GPU. The import
  now happens lazily inside the toast thread. `local_flow.py` only ever avoided this
  by accident of import order.

### ⚠️ Known constraint
**Whisper and Kokoro cannot both use CUDA in one process** — `torch` bundles cuDNN 9.1,
CTranslate2 needs 9.23, Windows allows one DLL per name per process, and the loser
segfaults (verified in both load orders). The merged engine therefore forces the voice
model onto the CPU and ignores `READER_DEVICE`. Kokoro-82M synthesises at ~2.7x
realtime there and loads faster than on GPU. Use `Launch_All.bat` for a GPU voice.
See ARCHITECTURE.md §12.

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
