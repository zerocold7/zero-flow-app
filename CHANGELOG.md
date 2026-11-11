# Changelog

All notable work on the **Zero- Flow Engine**. Newest first.

---

## [2.0.0] — in progress

### [2.0.0-alpha.9] — 2026-11-11 — Reader improvements (phase 6)

#### 🔊 Where and how much the Reader speaks
- **Reader output** on the Speech tab: the device the Reader speaks on, stored by name
  (`READER_OUTPUT`; blank is the Windows default). A name that is not plugged in falls
  back to the default for that run. Unplugged mid-read, the Reader moves to the default
  and plays the chunk that failed again, so the read carries on.
- **Long selections:** a read stops at 20,000 characters (about 20 minutes of speech),
  at the last whole sentence that fits. Rendering stays only four chunks ahead of the
  speaker. Measured before: a 50k-character selection held 296 MB of audio and kept a
  CPU busy for about 13 minutes.
- **F4 during a long read** now starts the new read. It used to do nothing while
  speech was still being rendered (on a CPU, about 80 s for 5,000 characters).

#### 🛟 CPU fallback
- If the graphics card fails to load the voice model, or fails while speaking, the
  Reader moves to the CPU once, says so in the Debug log, and carries on from the
  sentence that failed. Before, every F4 failed again until the Engine restarted.

#### Already in place, now checked
- Voice and speed were saved by 5b. spaCy's `en_core_web_sm` is installed from
  `requirements.txt`, and a test now fails if it is missing. Without it Kokoro would pip-install it
  on the first read. Smart mode adds no words to the Learned vocabulary (since the
  code review); its guard stays.
- Removed: `voice_engine.set_voice`, which nothing called.
- Arabic voice: research only, in `docs/research/arabic-tts.md`.

### [2.0.0-alpha.8] — 2026-11-11 — History, vocabulary and diagnostics (phase 5d)

#### 🗂️ What Zero- Flow keeps, through windows
- **Dictation history…** in the tray: every dictation, newest first, with a search
  (any case, English and Arabic), **Copy**, **Delete** and **Clear all** (asks first;
  the history only, unlike Shift+F2, which also clears the Debug log). With "Keep
  dictation history" off, the window says so and nothing is written. Copy keeps the
  text out of clipboard history.
- **Learned vocabulary…** in the tray: add, change and delete words, and **Tidy
  vocabulary**, which runs Shift+F1's own maintenance on a worker. A blank, repeated
  or sentence-long word is refused. Changes reach the next dictation with no restart.
- Both windows change the files as they are at that moment, under their locks, so a
  dictation or a learned word written while a window is open is never lost. Like
  Settings, they let go of the program's keys while open.

#### 🩺 Copy diagnostics
- **Copy diagnostics** in the tray puts on the clipboard the version, `detect()`'s
  facts, the settings in effect, whether a key is saved, the history and vocabulary
  counts, and the last 200 lines of each Debug log (Dictation's and the Reader's).
- It never holds a key, dictated words or the history. The saved key, anything shaped
  like a known key, and an address's user part and query are hidden. A log line that
  holds dictated words (now marked `[dictated]` when "Show dictated words in the log"
  is on) or the text of any history entry is replaced by a note that it was left out.
  Tests plant a key and words in every place they could leak from.

### [2.0.0-alpha.7] — 2026-11-11 — First-run wizard (phase 5c)

#### 🧭 Set up through a window
- **The wizard runs on a first start with nothing to migrate**, and again from **Run
  setup again** in Settings. Its screens: Interface language (Arabic switches it to
  right-to-left at once), This PC, Models folder, AI Provider, Downloads, Microphone,
  AI test, and a last screen with the keys. Nothing is written until Finish, so a
  wizard closed half-way runs again next time. Finish writes the settings file and
  restarts the Engine (about 5 s).
- **This PC** shows `check_hardware.py`'s `detect()` and `recommend()` unchanged
  (66 ms on this PC), with the reasons for the choice.
- **Models folder** is saved as `MODELS_DIR`, and every download goes there.
- **Downloads** show their measured size (pinned revisions, so the sizes are fixed),
  progress, speed and time left. Each runs in a child process that Cancel stops at
  once. A cancelled or failed download leaves nothing half-written. A model already in
  the folder is not downloaded again. The built-in AI runtime installs with progress.
- **Mic test** records 3 s and passes on a voice. **AI test** asks the chosen
  Provider one sentence through the Engine's own code. Each says plainly whether it
  passed or failed, and why.
- **The API key** goes to Credential Manager at Finish, before the settings file. The
  AI test hands it to its child process on standard input, never in a file.

#### 🔒 A new Windows account starts clean
- The program folder is shared by every Windows user. The old `.env`, vocabulary and
  history now migrate only when they belong to the user starting Zero- Flow; any other
  user gets the wizard, and nothing of the first user's is copied.

### [2.0.0-alpha.6] — 2026-11-11 — Tray, overlay and the Settings window (phase 5b)

#### 🪟 One program with a real interface
- **Qt replaces pystray.** The tray icon, a small **overlay** and the **Settings window**
  (PySide6) run on the Engine's main thread (ADR 0001). The tray menu: Dictation on,
  Reader on, Settings, Unload AI model, Open logs folder, Exit Engine.
- **One entry point, no console:** `Zero_Flow.pyw` (starts the project's `pythonw`).
  `Launch_Zero.bat` stays as a developer launcher with a console. The `.vbs` launchers
  and the Dictation-only and Reader-only launchers (`local_flow.py`, `Launch_Flow`,
  `Launch_Reader`) are gone; the Reader runs only as the Engine's child.
- **Overlay:** a pill at the bottom centre that never takes focus, lets clicks pass
  through and stays on top; it shows Recording (with a level meter), Transcribing, AI
  and Reading. A tooltip-type window, so Windows never activates it.
- **Dictation on / Reader on** apply at once, free the half's memory (the speech model
  and AI, or the Reader process and its voice model) and let go of its keys. Both off
  is **Paused**. Both are saved (`DICTATION_ON`, `READER_ON`).
- **Saving other settings restarts the Engine:** the old one starts the new one with
  `--restart`, which waits up to 10 s for the single-copy claim. Measured on this PC:
  5.3–5.4 s until Dictation can run (`tools/measure_restart.py`).
- **Hotkeys:** "press a key" boxes. Esc and Windows-key combinations are refused, a key
  already in use is reported by name, F5 and F7 warn (browsers and Office use them).
  The window says it cannot see other apps' keys.
- **Microphone** picked by name (`MICROPHONE`); one that is unplugged falls back to the
  Windows default with one toast, and is used again when it returns.
- **AI Provider** is now Built-in, Ollama or Custom. `openai` and `claude` in an old
  settings file are read as Custom (Claude is a preset). A Custom provider that is not
  on this PC shows "your dictated text is sent to this server". The API key goes to
  Credential Manager only, and a failed save changes nothing.
- **Other new settings:** `INTERFACE_LANGUAGE` (English and Arabic ship; Arabic switches
  to right-to-left), `LANGUAGE_PAIR`, `KEEP_HISTORY`, `READER_SPEED`; *Start with
  Windows* is the HKCU Run key, not the file.
- **Removed:** the Reader's own tray menu (voice, speed and Smart mode are settings now),
  `Pillow` and `pystray` (no longer used).

### [2.0.0-alpha.5] — 2026-11-11 — Settings, vocabulary and history move out of the program folder

#### 🗂️ One settings file (phase 5a)
- **Settings live in `%APPDATA%\ZeroFlow\settings.json`**, a JSON object of
  `"NAME": value`. It is the only source; restart the engine after editing it. A Settings
  window will replace hand-editing in phase 5b. Developers can point `ZEROFLOW_SETTINGS`
  at another settings file; its folder then holds the vocabulary and history too.
- **First start only:** with no `settings.json`, the engine reads the old `.env` once
  (same checks as before), writes `settings.json`, and copies `flow_vocabulary.txt` to
  `vocabulary.txt` and `flow_history.md` to `history.md` in `%APPDATA%\ZeroFlow`. The
  old files are never changed and never read again. `.env.example` stays as the optional
  import template.
- **The API key leaves the file.** `AI_API_KEY` is never in `settings.json`: the first
  start moves it from `.env` to Windows Credential Manager, as `ZeroFlow:<address>`
  (`ZeroFlow:https://api.anthropic.com` for Claude). A start-up notice says the old
  `.env` still holds the key, so its line can be deleted. Claude still works with
  `ANTHROPIC_API_KEY` or `ant auth login` when no key is stored.
- **Logs moved** to `%LOCALAPPDATA%\ZeroFlow\logs\`: `flow_debug.log`,
  `reader_debug.log`, `flow_crash.log`, `reader_crash.log`, `builtin_ai.log`.
- **Models folder:** the new setting `MODELS_DIR`. Default: `HF_HOME` if set, otherwise
  `%LOCALAPPDATA%\ZeroFlow\models`. Models are not downloaded again if it points where
  they already are.
- **`check_hardware.py --apply`** writes into `settings.json` once it exists; before the
  first start it writes into `.env`, which the first start moves in.

#### 🧹 Nine settings gone
- `HOTKEY_PANIC` (`Esc` always cancels and silences), `AI_NUM_CTX` and `OLLAMA_NUM_CTX`
  (8,192), `AI_BUILTIN_PORT` (39281), `READER_SMART_MAX_CHARS` (1,000),
  `READER_LLM_TIMEOUT` (10 s), `READER_FIRST_BATCH_CHARS` (120) and `READER_BATCH_CHARS`
  (300) are fixed values in the code now. `FALLBACK_LLM` is removed: with Ollama down or
  empty, no model name is guessed. An old `.env` that names them still migrates quietly.

#### 🛡️ Safeguard
- **A model folder missing a file is repaired.** If a cached Whisper model folder lacks a
  file, or has an empty one, the engine downloads the missing files at the pinned revision.

#### 📝 Docs
- `CONFIGURATION.md`, the install, hardware, FAQ and beginner guides (English and
  Arabic), `ARCHITECTURE.md`, the presets and the launchers' messages now name the new
  places.
- **The guides are Markdown only.** The printable PDFs of the beginner guide and their
  builders (`tools/build_setup_pdf.py`, the Word-based Arabic build) are gone, with
  `reportlab` from the dev tools: two copies of every guide drifted, and the Arabic one
  needed Word to rebuild.

---

### [2.0.0-alpha.0 – 2.0.0-alpha.4.5] — 2026-10-14 to 2026-11-04 — Stability, accuracy, structure, the built-in AI, the security audit (phases 1–4)

#### 🛡️ Stability (phase 1)
- **Quick presses no longer mix up recordings.** Every recording shared one audio
  queue and one "recording" and "cancel" flag. Stop-then-start within 40 ms kept the
  first recording running and wiped its audio; Esc followed by a record key could still
  paste the cancelled clip; a microphone that failed late stopped the *next*
  recording. Each recording now has its own state (`Capture`).
- **A forgotten recording stops itself** after `MAX_RECORDING_SECONDS` (300 s) and is
  transcribed as usual. It used to grow by ~4 MB a minute.
- **"AI unavailable" instead of "Polished".** When the AI did not answer, Polish
  printed "✨ Polished" and Translate "Translated" over your unchanged words. An empty
  answer pasted nothing; it now counts as no answer.
- **With Ollama down at the first Polish**, the fallback model was kept for the whole
  session, so every request after Ollama started failed with a 404. A 404 at start-up
  was also logged as "loaded".
- **Shift+F3** passes its answer through the language guard, waits for Shift to come
  up (Ctrl+C with Shift held is Ctrl+Shift+C), and says when the AI is down.
- **Vocabulary:** a learned word appended to a file without a final newline glued onto
  the last word ("VisaKokoro"); writes now share a lock, so `Shift+F1` keeps a word
  learned while it ran; and the model's chatter ("Here is the cleaned list:") is no
  longer saved as words.
- **History** is capped as it is written, not only at start-up, and trimmed at an
  entry boundary.
- **Out of graphics memory mid-dictation**, a clip is retried on a CPU copy of the
  speech model. It used to be lost, and logged as "silence".
- **One copy at a time.** A second engine says it is already running and closes; two
  pasted every dictation twice.
- **The reader is supervised:** a crash restarts it (after 2, 4, 8 s, then gives up
  and says so). It used to exit with code 0, so F4 died silently. It is tied to the
  engine with a Windows Job Object, so a crashed engine no longer leaves it running.
  A standalone reader's Exit no longer shuts down a full engine.
- **Crashes leave a trace:** uncaught errors on any thread go to the debug log, native
  crashes to `flow_crash.log` / `reader_crash.log`, and a fatal error shows a message
  box — a hidden engine's console is never seen.
- **Hidden launches leave nothing behind:** each exit of a `*_Silent.vbs` launch left
  an invisible `cmd.exe` waiting for a key. Visible launchers now pause only after an
  error.

#### 📦 Install
- **`constraints.txt` pins every package** to a set known to work together; install
  with `pip install -r requirements.txt -c constraints.txt`. Without it, a fresh install
  took transformers 5.19, which needs a newer torch, and the reader could not start.
- The spaCy English model is a listed requirement; Kokoro used to pip-install it on the
  first read (a hidden download, and a failure offline).
- `requirements-dev.txt` and a `ruff` configuration for working on the engine.

#### 🎯 Accuracy and speed (phase 2)
- **Invented endings are dropped.** A stock ending — "Thank you.", "Have a good
  night.", "شكرا للمشاهدة", "اشتركوا في القناة" — is removed from the very end of a
  dictation when the audio shows it was never said: it sits 15 dB or more below your
  speech (a breath, typing, the room), or Whisper was unsure of its own words. A
  clearly spoken "thank you" stays. Each drop is logged with its evidence.
- Whisper's retries stop at temperature 0.4 instead of 1.0, where a retry is close to
  guessing.
- **0.6 GB of graphics memory back.** The AI's context is set to 8,192 tokens
  (`OLLAMA_NUM_CTX`); gemma4-e4b's model file asked for 131,072 — 3.58 GB against
  2.99 GB, measured, with the same speed and answers. The warm-up sends the same
  setting, so the first Polish still takes 0.3 s.
- **Measured, not adopted:** `large-v3-turbo` is as accurate in English and 35% faster,
  but far worse in Arabic (56% vs 35% character errors) — documented as an
  English-only option. An answer-length cap for the AI saved nothing measurable and
  could cut long dictations short.
- **`tools/bench/`:** a speech benchmark that runs the engine's own transcription on
  132 synthetic cases (clean, room noise, breath, typing, quiet, no speech) and on
  recordings of your own voice (`record_mine.py`, kept on your PC), plus an AI-model
  benchmark for memory and speed.
- The unused auto-detect path in transcription is gone; every key forces its language.
- CONFIGURATION.md's "change a language" recipe now says the Polish prompt must change
  too — the English one answers in English only.

168 tests. The filter changed no error rate on the synthetic clips and kept every real
"thank you" in them.

153 tests at the end of phase 1 (from 109). Each fix was broken on purpose to confirm
its test fails.

#### 🧱 Structure (phase 3)
- **The engine is a package, `zeroflow/`.** `local_flow.py` (975 lines), `flow_core.py`,
  `engine_ui.py`, `flow_signals.py` and `personas.py` became small modules — `engine`,
  `stt`, `llm`, `capture`, `clipboard`, `settings` and others (map in ARCHITECTURE.md).
  `local_flow.py` and `zero_flow.py` stay as entry points, so the launchers are
  unchanged. Code was moved verbatim, and every one of the earlier deliberate breaks is
  still caught by its test.
- **A typo in `.env` no longer stops the engine.** Every setting is checked; a value that
  does not fit ("five" seconds, "gpu" for auto-or-cpu) is reported by name in the
  console, the log and a toast, and the default is used. Yes/no settings take
  true/false, yes/no, on/off or 1/0. `.env` is read from the program folder, wherever
  the engine was started from.
- **Choose the AI server in `.env`:** `AI_PROVIDER="openai"` with `AI_URL`, `AI_MODEL` and
  (for a cloud service) `AI_API_KEY` talks to LM Studio, the llama.cpp server, vLLM,
  OpenAI or Groq — no code to paste any more. Ollama stays the default.
- **Shift+F3 copies the line the way F4 does** — waiting up to half a second for slow
  apps, where it read the clipboard once after 50 ms.
- One start-up banner, one copy routine, one URL pattern, one settings file (the
  reader's settings included); the reader also drops `www.` addresses before speaking.
- Type hints on every function in `zeroflow/`; `ruff` passes on the whole project.

196 tests.

#### 🧠 The AI built in (phase 4)
- **No Ollama needed.** The engine runs llama.cpp's `llama-server` itself, as a hidden
  child process tied to the engine (a crash or End task takes it down too), with
  Google's **Gemma 4 E4B** (Apache 2.0), downloaded once on first start (5.15 GB). It is
  the new default (`AI_PROVIDER="builtin"`); Ollama stays one setting away.
- **Faster than Ollama, the same answers.** Measured on an RTX 4070: loads in 3.1 s
  (Ollama 6.8–7.1 s), a Polish takes 0.26 s (0.37 s), 3.2 GB of graphics memory — 9.3 of
  12.3 GB with Whisper and the voice. Through the real engine the AI is ready 5.4 s after
  start-up. Gemma's "thinking" is switched off: with it on, Polish took 2.4–7.8 s.
- **`tools/get_llama.py`** installs the runtime for the PC's graphics: `cuda` (NVIDIA,
  625 MB), `vulkan` (AMD Radeon / Intel Arc, 31 MB) or `cpu` (19 MB), from the pinned
  llama.cpp release b11619. Every archive is checked against its published SHA-256 and
  refused if it differs or would write outside its folder. Without it, the engine says
  so at start-up and uses Ollama.
- **One server for both halves:** it listens on a fixed local port, so the reader uses
  the engine's server instead of loading the model a second time. A server that stops is
  restarted on the next request, and the log says so (`builtin_ai.log`).
- **Hardware tiers** pick the build, and Google's smaller **Gemma 4 E2B** (3.35 GB) for a
  4–5 GB laptop card or 8 GB of RAM; the banner names whichever model runs. Not yet
  tried on real hardware: the Vulkan build, and E2B's Arabic.
- **Your own API key:** `AI_PROVIDER="claude"` uses Anthropic's Claude (`AI_API_KEY`;
  `claude-opus-5-5` unless `AI_MODEL` names another), through Anthropic's SDK, with the
  server-side refusal fallback on. `AI_PROVIDER="openai"` covers OpenAI-format services.
  A rejected key, a refusal or an outage pastes your own words, and says why.
- `check_hardware.py` reports whether the built-in AI is installed and its model
  downloaded, and asks Ollama only when it is the provider; `--apply` keeps an AI
  provider or model you chose.

- **Docs:** the install guides, both beginner guides (and their PDFs), HARDWARE,
  CONFIGURATION §6 (every provider), the FAQ and ARCHITECTURE describe the built-in AI.

238 tests. Each new guard was broken on purpose to confirm its test fails.

#### 🧠 Unload the AI when you do not need it
- **Tray → Unload AI model** frees the AI's memory at once — 3.2 GB of graphics memory
  with the built-in AI, measured (Ollama is told to drop its model; a cloud AI has
  nothing on your PC to free). The next Polish, Translate, line fix or Smart clean
  loads it again by itself: that one takes ~4.5 s instead of ~0.5 s, and the window
  says "Loading the AI model...".
- **`AI_LOAD_AT_START="False"`** keeps the AI out of memory when the engine starts,
  until the first Polish needs it. The default (`True`) still loads it with Whisper.

257 tests; the five new guards were each broken on purpose and caught.

#### 🧹 Checked and cleaned (phases 1–4)
A top-to-bottom review before the app window, with nothing in it changing what you see
except where noted.
- **Your voice is never written to disk.** Each clip went to Whisper through a
  temporary `flow_capture.wav`; it now goes from memory. Measured on 127 synthetic
  clips and your own recordings: the same errors and no invented words either way,
  0.05–0.15 s faster per synthetic clip. `SAMPLE_RATE` and `CHANNELS` are no longer
  settings — Whisper's format is fixed, and another value would only have broken it.
- **Phase 2's open question, settled:** capping the volume boost for quiet clips
  (10×) made quiet Arabic worse (55% → 58% character errors) and invented nothing
  less, so the full boost stays.
- **One place for every AI answer.** The spinner, the empty-answer check and learning
  a `[LEARN: …]` word happen once, in `zeroflow.llm.ask_ai`, instead of in each
  provider. With the AI unreachable, `Shift+F1` now says so instead of "unchanged".
- **Ollama leftovers gone:** the reader's banner named Ollama's setting (blank with
  the built-in AI), window titles said "OLLAMA PROCESSING", and the presets picked an
  Ollama model per tier — which made `check_hardware.py` print "Keeping your own AI
  model…" to people not using Ollama.
- **Launchers:** `Launch_All.bat` and its silent twin are gone — `Launch_Zero.bat`
  runs both halves in one window, both on the graphics card. `Launch_Silent.vbs` is
  now **`Launch_Flow_Silent.vbs`**, like its siblings (update a shortcut that used it).
- Smaller: a one-function reader module folded into the reader, duplicated set-up in
  the logs and Windows-signal modules removed, the version string says alpha.4, and
  the deliberate-break checks (64, all caught) follow the moved code.

244 tests. The engine was run end to end with the real models: Polish and Translate in
both languages in 0.33–0.43 s, the AI ready 4.6 s after start, and no `llama-server`
left after a crash.

#### 🛡️ Safeguards
- **An AI that fails keeps your words.** A provider that broke instead of answering
  (a server reply in an unexpected shape, a missing package) lost the whole dictation;
  now your own words are pasted, a toast says the AI failed, and the log says why.
- **Your clipboard comes back even when a paste fails** partway, rather than being
  left holding the dictation.
- **Start-up warns about** two actions set to one key in `.env` (both would run on
  every press; `alt+ctrl+r` and `Ctrl + Alt + R` count as the same key), an
  `AI_BUILTIN_PORT` above 65535, and an `AI_API_KEY` sent over plain `http://` to
  another computer.

266 tests; the seven new guards were each broken on purpose and caught (76 in all).

#### 🔒 Privacy and security (audit)
- **Your words stay out of the debug log.** `flow_debug.log` recorded every dictation
  word for word, twice (the transcript and the pasted text), and the AI's answer when
  it was in the wrong language. It now records their size; `LOG_DICTATION_TEXT=True`
  brings the words back for debugging. The history file is unchanged.
- **Your clipboard stays on your PC.** Polish sent up to 500 characters of the
  clipboard (often a password just copied) as context to any AI, Claude and cloud
  services included. `POLISH_CLIPBOARD_CONTEXT=auto` (the default) now gives it only
  to an AI on this PC; `on` and `off` override.
- **Spoken commands come from what you said.** "New line", "bullet" and "format code"
  were read from the AI's answer, so clipboard text could steer Polish into adding
  one, and Translate translated "سطر جديد" away. They are now taken from what you
  said, before the AI sees it.
- **"اشتركوا في القناة" is no longer added.** In a live test, Arabic Polish pasted
  "…وأنت اشتركوا في القناة" after a word Whisper did not know: the stock phrase sat on
  real speech, loud and confident, so the invented-ending filter (which goes by the
  audio) kept it. Endings only video subtitles have — "اشتركوا في القناة", "شكرا
  للمشاهدة", "thanks for watching", translation credits — are now dropped from the end
  whatever the audio says; "thank you", "شكرا" and "thanks for listening" still follow
  the audio. Measured first: two general fixes (faster-whisper's
  `hallucination_silence_threshold`, a shorter Arabic hint) gained nothing, and the
  hint cost quiet Arabic badly (55% → 92% errors). English showed no invented words in
  any test.
- **The Enter command is gone.** "and send" / "انتر" was meant to press Enter after
  the paste; in use it misfired ("and enter" and the Arabic "وانتر", with "and" joined
  to the word, were typed as words) and the AI could be steered into it. The engine
  now only types what you said: no key is ever pressed after a paste.
- **Packages with known security holes upgraded:** Pillow 10.2.0 → 13.0.0, requests
  2.31.0 → 2.33.0, urllib3 → 2.8.0, python-dotenv → 1.2.2, filelock → 4.2.1, and
  certifi, anyio, fsspec, setuptools. `pip-audit` (now in `requirements-dev.txt`)
  finds none left in them.
- **torch 2.5.1+cu121 → 2.14.1+cu126** (12 known holes, among them `torch.load`
  running code from a crafted weights file), with sympy 1.14.0, which it needs.
  **On NVIDIA PCs, install it with the new command in [INSTALL.md](docs/INSTALL.md)
  first;** a plain `pip install -r … -c constraints.txt` would replace the old one
  with the CPU-only build. The reader's voice runs on the card as
  before (0.08 s for 4.3 s of speech, the same as 2.5.1); its cuDNN is now 9.10, still
  not Whisper's 9.23, so the two halves stay separate processes.
- **Your clipboard comes back whole, and dictations stay out of Win+V.** The clipboard
  was saved and restored as text only (pyperclip), so a picture or copied files were
  gone after every dictation, `F4` and `Shift+F3`; and every dictation landed in
  clipboard history and cloud sync. The new `zeroflow/win_clipboard.py` saves every
  format through the Win32 API and marks the engine's own writes as private. Checked
  on the real clipboard: a picture survives, and a dictation is absent from Win+V
  history while an ordinary copy is present. pyperclip is no longer needed.
- **Models download at a fixed version.** Whisper, the built-in AI's Gemma and the
  reader's voice were fetched at whatever was uploaded last, so a changed or tampered
  upload would reach the next fresh install. `zeroflow/models.py` now pins each to a
  Hugging Face commit — the versions already in use, so nothing downloads again.
- **Two quick `F4` presses start one read.** The reader's "busy" flag was checked and
  set a few steps apart, so a second press in between started a second selection copy
  and a second read. A lock now covers the whole read.

305 tests (6 more on the real clipboard with `ZEROFLOW_REAL_CLIPBOARD=1`); each fix
was broken on purpose and caught.

#### 🪶 Lighter install
- **The Claude package is an optional install.** Every install carried `anthropic` and
  the 7 packages it pulls in, used only with `AI_PROVIDER=claude`. It is now one extra
  command for those who choose Claude ([CONFIGURATION.md §6](CONFIGURATION.md)); without
  it, start-up says so, names the command, and uses the built-in AI.
- **`soundfile` moved to `requirements-dev.txt`**: only the bench tools use it.
- **`tests/test_requirements.py`** keeps the lists honest: everything the engine imports
  is installed, everything installed is used, and `constraints.txt` pins exactly what an
  install pulls in.
- `logo.jpg` 437 KB → 13 KB (680 px wide, shown at 340; the same at that size).
- **The laptop guide no longer edits `requirements.txt`.** It had CPU laptops delete
  the two `nvidia-` lines by hand, which leaves a changed file that stops the next
  `git pull`. Every guide now skips those lines with the same three-line command
  (`docs/INSTALL.md` step 4), short enough to copy from the printed PDFs without
  breaking; both PDFs are rebuilt. **If you edited it**, run
  `git checkout requirements.txt` before updating.
- **Python other than 3.12 is named**, by `check_hardware.py` and at start-up: 3.12 is
  the only version tested, and on another the packages may not install or run.
- **The voice starts sooner after a long first sentence.** A batch was always at
  least a whole sentence, so a 223-character opening meant 3.4 s of silence on the
  processor; it is now split after a comma: 1.5 s (0.6 s with
  `READER_FIRST_BATCH_CHARS=60`). That also makes the setting do what the guides say.
- **Measured, left as is:** the voice's ~11 s load is library imports (torch,
  transformers, kokoro), 2.8 s of it one scan of every installed package inside
  transformers; it runs in the background at start-up. The engine uses no processor
  while idle. `tools/bench/measure_load.py` gives these numbers.

#### 🧪 Every case tested
391 tests (from 266 at alpha.4.3); test coverage 87% of the engine (from 77%). New:
the whole engine's life (starting the reader, Exit from the tray, a stuck reader at
shutdown, a crash, a second copy); every signal between the halves on real Windows
objects under names of their own; Shift+F2; a microphone that will not open, a clip
too short or cancelled, the five-minute limit; Smart cleaning's four outcomes,
suspend, voice and device choice. `tools/mutation_check.py` breaks 96 guards on
purpose — every fix since the audit included — and each one's test catches it.
What stays untested on purpose: what is drawn on screen (console, tray, toasts) and
sound itself, which `tools/smoke_check.py` checks for real.
- **`tools/smoke_check.py`** checks every real part on a PC end to end: settings, the
  microphone and speaker, Whisper in English and Arabic, an AI Polish, the voice.
- **One home per fact.** Why the reader is a separate process was told in full three
  times (now only ARCHITECTURE.md §12); the Whisper model table twice, already
  drifting apart (now only HARDWARE.md §4); install steps in CONFIGURATION.md and
  requirements.txt, one of them out of date (now only INSTALL.md step 4). The others
  point there, and `tests/test_docs_links.py` checks that all 134 links between the
  guides lead to a real file and heading.

#### 🔍 Code review
A full review of the engine found ten faults; each is now a test that failed first
(`tests/test_review_findings.py`):
- **A busy clipboard after the paste** threw your clipboard away and failed a dictation
  that had already been pasted. It is now put back a moment later, and the dictation
  is written to the history before the paste, so it is never lost.
- **Shift+F3 during a Polish** could garble the line: it now waits for the dictation.
- **The reader could speak into an open microphone** when dictation started while it
  was preparing the text; that read is now dropped.
- **The clipboard could reach a remote Ollama** when the built-in AI fell back to it:
  `POLISH_CLIPBOARD_CONTEXT` is now decided by the AI actually in use.
- **A Polish during the AI's first start** waited with no limit, holding every
  dictation behind it; it now gives up after its timeout and pastes your words.
- **`[LEARN: …]` was honoured on every AI call**, so selected text could teach a
  "word"; only English Polish learns now, a term is at most four words, and Shift+F1
  drops Chinese, Japanese and Korean script.
- **The record keys printed inside Windows' keyboard hook**; a frozen console could
  make Windows remove the hook. They now only change state there.
- **A wrongly named key** (`HOTKEY_FIX="f55"`) stopped the engine; it now falls back to
  the default and says so, like every other setting.
- **Every AI answer waited a fixed 0.15 s** for the spinner; it now stops at once.
- **A slow health check could start a second AI server** and orphan the first.

Not changed: another program holding the AI's port on the same PC (needs a second
user on it), and how long a huge Excel copy takes to save (not measured).

---

## [1.5.1] — 2026-10-14 — A fresh install works again

### 🐛 Fixed
- **A fresh install could not start the reader.** `requirements.txt` named only the
  top-level packages, so pip took the newest of everything underneath. transformers
  5.19 needs torch 2.6 or later, while the engine uses 2.5.1 — the voice model then
  failed to load (`module 'torch' has no attribute 'accelerator'`), on an install where
  nothing in this project had changed. Installs made before that release were fine.

### 📦 Install
- **`constraints.txt`** pins all 122 packages to the set 1.5.0 was built and tested
  with. Install with `pip install -r requirements.txt -c constraints.txt`; every guide
  now says so (English and Arabic). `torch==2.5.1` there matches both the CUDA build
  NVIDIA PCs install first and the regular one CPU-only PCs get.
- **The spaCy English model** is a listed requirement. Kokoro used to pip-install it at
  run time on the first read — a hidden download, and a failure when offline.

### 📄 Guides
- **The Arabic beginner guide is now a PDF** (`docs/Zero-Flow-Setup-Guide.ar.pdf`), like
  the English one; the Word file is gone. Word still does the Arabic layout, as an
  in-between step (`tools/build_setup_ar_pdf.ps1`).

**Already installed and working?** Nothing to do. To align an existing install with
the tested set: `.\venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints.txt`.

No engine code changed.

---

## [1.5.0] — 2026-09-24 — Arabic that stays Arabic, and a faster start

### ⚡ Faster
- **The engine is ready ~5 s sooner** (10.2 s → 5.0–5.3 s to a loaded model on an
  RTX 4070). CTranslate2 imported torch and transformers on every start — about 6 s —
  for model converters this engine never uses. `local_flow.py` now skips that optional
  import, so torch never loads in the dictation process at all. Transcription is
  unchanged; the reader, a separate process, still loads torch for its voice.
- **The test suite runs in ~2 s instead of ~8 s** (36 s on a cold disk), for the same
  reason: three test files import `local_flow`.
- **The playback tests no longer sleep.** Each ended with a fixed 50 ms pause, guessing
  when the playback worker had finished with the fake audio device. They now send a
  marker through the worker and wait for it to come out the other side — exact rather
  than a guess, and 13 ms per test instead of 58. Both versions passed 600 runs with
  every CPU thread saturated, so the old guess held on this machine; the new one does
  not depend on it.

### 🌍 Arabic
- **Arabic Polish and English → Arabic often answered in Chinese.** The engine used
  `qwen2.5:7b`, which answered the old Arabic Polish prompt in Chinese 5 times out of 5
  (10 of 15 Arabic tasks in all). Three fixes:
  - **Arabic-specific prompts.** `ARABIC_POLISH_PROMPT` writes Modern Standard Arabic,
    removes fillers and fixes hamza, ة/ه and ى/ي. The English → Arabic prompt says
    "Arabic script only" and names the dual.
  - **A language guard.** Every AI answer must be in the language the key asked for,
    with no Chinese, Japanese or Korean script — otherwise your own words are pasted.
    Checked against real qwen: 5 Arabic Polishes, zero Chinese pasted.
  - **Gemma 4 E4B instead of qwen** on the reference PC. It writes the best Arabic of
    the three installed models (MSA, correct dual, no drift), uses 2.3 GB less graphics
    memory, and is ~0.3 s slower on English.
- **Whisper was primed with English for Arabic.** Every dictation's hint was one shared
  list — mostly Latin-script tech words plus three misheard "learned" Arabic words.
  Arabic now gets a short punctuated Arabic sentence (`ARABIC_WHISPER_HINT`), English
  the Latin terms. On 16 Arabic clips, through the engine's own code, repeated:
  character errors **49.8% → 39.7–40.2%**, and sentences ending in `.`/`؟`
  **1 → 14 of 16**.
- **The vocabulary taught itself junk.** Words are now learned only if they appear in
  what was said, never in CJK script, and only from English Polish. Words learned
  before this are kept: open `flow_vocabulary.txt` and delete any you never said (the
  reference PC had three — مادرانتي، ظانيم، هوكوري), since Arabic ones go into the hint.
- **Arabic spoken commands fired on ordinary sentences** — "نقطة البداية…" became a
  bullet, "كود الخصم…" code. Bullets now need **قائمة**, code **تنسيق كود**. "نقطة" at
  the end still types a full stop.
- The AI's Arabic loses the vowel marks models add unasked (tanween on alif stays).

### ⚡ Faster AI
- **`think: false` on every request.** Gemma 4 is a reasoning model and wrote ~800
  hidden tokens before each one-line answer: 5–9 s instead of ~1 s, for the same result.
- **The model loads at start-up and stays loaded** (`OLLAMA_KEEP_ALIVE`, default 30
  min). The first Polish after starting takes 0.8 s instead of a 7–12 s load, and
  dictation is ready ≤0.7 s later than before.
- `check_hardware.py --apply` no longer replaces an AI model you pinned yourself.

### ✨ Added
- `tests/test_startup.py` — fails if the skip stops working after a CTranslate2
  upgrade, or leaves torch unimportable for code that needs it.
- `tests/test_arabic.py` and additions to the vocabulary and hardware tests — the
  hint per language, the language guard, vowel marks, the new triggers, `think` and
  `keep_alive`, learn-only-what-was-said (109 tests in all).

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
- **`tools/`** — the scripts that rebuild the printable PDF and the Arabic Word file
  from the Markdown guides, so those two generated files cannot drift again.

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
