# Configuration & Customization Guide

How to tweak Zero- Flow. Most things are changed in **`settings.json`** (no code). The
deeper ones (prompts, voice macros) are small, clearly-marked edits in the code.

One `settings.json` configures **both halves** — dictation (`zeroflow/engine.py`) and the
reader (`reader/`). Reader-only settings are in §10.

> After changing **`settings.json`** you must **restart** the engine. Changes to the code
> (`zeroflow/`, `reader/`) also require a restart.

---

## 1. `settings.json` reference
Your settings live in one file: **`%APPDATA%\ZeroFlow\settings.json`** (paste that into
the Explorer address bar to open the folder). It is a JSON object with one `"NAME": value`
line per setting. A value is `true` or `false`, a number, or text in quotes:

```json
{
  "WHISPER_MODEL_NAME": "small",
  "WHISPER_DEVICE": "cpu",
  "AI_LOAD_AT_START": true,
  "MAX_RECORDING_SECONDS": 300
}
```

It is the only source: nothing else is read. A setting you leave out has its default, so
you only set what you want to change. A value that is not what its setting needs (a word
where a number goes) does not stop the engine: the default is used and the start-up
window names the mistake. Restart the engine after editing the file.

A Settings window will replace hand-editing in a later step (Phase 5b). Until then you
edit `settings.json` with Notepad.

> **The first start.** When there is no `settings.json`, the engine looks for the old
> `.env` in the program folder, once. If there is one, it reads it with the same checks as
> before, writes `settings.json`, and copies `flow_vocabulary.txt` to
> `%APPDATA%\ZeroFlow\vocabulary.txt` and `flow_history.md` to
> `%APPDATA%\ZeroFlow\history.md`. The old files are never changed and never read again.
> So a new user may copy `.env.example` to `.env` before the first start, or simply start
> and then edit `settings.json`. An old `.env` that names a setting that no longer exists
> (see the end of this section) migrates quietly.
>
> **Developers:** point the environment variable `ZEROFLOW_SETTINGS` at another settings
> file. Its folder then also holds the vocabulary and the history.

> **The hardware-dependent settings have a shortcut.** `python check_hardware.py
> --apply` detects your PC and writes the model and device settings for it (into
> `settings.json` once it exists; before the first start, into `.env`, which the first
> start then moves in). `presets/` holds the same values as one file per kind of hardware.
> What each tier means, with measured speeds: [docs/HARDWARE.md](docs/HARDWARE.md).

| Setting | Default | What it does |
|----------|---------|--------------|
| `WHISPER_MODEL_NAME` | `large-v3` | Speech model — accuracy vs. speed/VRAM (see §3) |
| `WHISPER_DEVICE` | `auto` | `auto` = NVIDIA GPU, falling back to CPU · `cpu` = skip the GPU (see §5) |
| `WHISPER_COMPUTE_TYPE` | `float16` | GPU precision; `int8_float16` halves graphics memory (see §5) |
| `AI_PROVIDER` | `builtin` | Which AI runs Polish and Translate: `builtin` (inside the engine), `ollama`, `openai` (any server speaking the OpenAI chat format) or `claude` (see §6) |
| `LLAMA_VARIANT` | `auto` | The built-in AI's build: `auto` (from the graphics card), `cuda`, `vulkan` or `cpu` |
| `AI_BUILTIN_REPO` / `AI_BUILTIN_FILE` | Gemma 4 E4B | The built-in AI's model on Hugging Face (Gemma 4 E2B is smaller — see §6) |
| `AI_LOAD_AT_START` | `true` | Load the AI while Whisper loads, so the first Polish is instant. `False` keeps it out of memory until the first Polish or Translate needs it (that one waits ~4 s). Tray → **Unload AI model** frees it at any time |
| `AI_URL` / `AI_MODEL` | *(blank)* | For `openai` and `claude` (see §6). The API key is not a setting: it lives in Windows Credential Manager (§6 D) |
| `POLISH_CLIPBOARD_CONTEXT` | `auto` | Polish hands the AI your clipboard as context. `auto` = only to an AI on this PC (never to `claude` or a server on another computer) · `on` = always · `off` = never (see §6) |
| `OLLAMA_HOST_URL` | `http://127.0.0.1:11434/api/generate` | `ollama` only: where Ollama listens |
| `OLLAMA_MODEL_NAME` | *(blank)* | `ollama` only: pin an exact model, e.g. `qwen2.5:7b`. Blank = auto-pick the first model Ollama serves |
| `MAX_RECORDING_SECONDS` | `300` | A recording left running stops by itself after this many seconds, and is transcribed as usual |
| `ENABLE_AUDIO_CHIMES` | `true` | Beeps on start/stop/success |
| `ENABLE_TOAST_NOTIFICATIONS` | `true` | Windows toast pop-ups |
| `LOG_DICTATION_TEXT` | `false` | `flow_debug.log` records each dictation's size, not its words. `true` writes the words too, for debugging (see §9) |
| `HOTKEY_*` | see §2 | Key bindings |
| `HOTKEY_READ` | `f4` | Read the highlighted text aloud (see §10) |
| `READER_VOICE` | `af_heart` | Which Kokoro voice speaks (see §10) |
| `READER_SMART_MODE` | `false` | LLM-clean captured text before speaking (see §10) |
| `READER_DEVICE` | `auto` | `auto` / `cpu` / `cuda` for the voice model (see §10) |
| `OLLAMA_KEEP_ALIVE` | `30m` | `ollama` only: how long the AI model stays loaded after use. The engine also loads it at start-up, so the first Polish is instant. `0` unloads at once (frees memory) |
| `MODELS_DIR` | `HF_HOME` if that environment variable is set, otherwise `%LOCALAPPDATA%\ZeroFlow\models` | The folder the speech, voice and built-in AI models are kept in (see §3) |

**Fixed values.** Nine settings from earlier versions no longer exist. Each is a fixed
value in the code now, or was removed. An old `.env` that names them still migrates
quietly; in `settings.json` they would do nothing.

| Was | Now |
|---|---|
| `HOTKEY_PANIC` | `Esc` always cancels a recording and silences the reader |
| `AI_NUM_CTX`, `OLLAMA_NUM_CTX` | 8,192 tokens of working memory: enough for a five-minute dictation and its answer (gemma4-e4b's own setting, 131,072, held 0.6 GB more graphics memory for nothing) |
| `AI_BUILTIN_PORT` | 39281 |
| `FALLBACK_LLM` | removed: with Ollama down or empty, no model name is guessed |
| `READER_SMART_MAX_CHARS` | 1,000 characters: longer selections skip the LLM pass |
| `READER_LLM_TIMEOUT` | 10 seconds to wait for the LLM before speaking anyway |
| `READER_FIRST_BATCH_CHARS` | 120 characters in the first chunk sent to the voice |
| `READER_BATCH_CHARS` | 300 characters in every chunk after the first |

---

## 2. Changing hotkeys
Each binding is a `HOTKEY_*` setting in `settings.json`. The value is a key name in
[`keyboard`](https://github.com/boppreh/keyboard) syntax: `f5`, `ctrl+shift+d`,
`alt+space`, `print screen`, etc.

```json
{
  "HOTKEY_EN_RAW": "f5",
  "HOTKEY_EN_POLISH": "f6",
  "HOTKEY_AR_RAW": "f7",
  "HOTKEY_AR_POLISH": "f8",
  "HOTKEY_EN2AR": "f9",
  "HOTKEY_AR2EN": "f10",
  "HOTKEY_FIX": "shift+f3",
  "HOTKEY_MAINTENANCE": "shift+f1",
  "HOTKEY_PURGE": "shift+f2",
  "HOTKEY_READ": "f4"
}
```

| Setting | Does |
|---|---|
| `HOTKEY_EN_RAW` / `HOTKEY_AR_RAW` | English / Arabic, raw |
| `HOTKEY_EN_POLISH` / `HOTKEY_AR_POLISH` | English / Arabic, AI cleanup |
| `HOTKEY_EN2AR` / `HOTKEY_AR2EN` | Translate English → Arabic / Arabic → English |
| `HOTKEY_FIX` | fix the current line |
| `HOTKEY_MAINTENANCE` | vocabulary maintenance |
| `HOTKEY_PURGE` | clear the debug log and history |
| `HOTKEY_READ` | read the highlighted text aloud (reader) |

`Esc` is not a setting: it always cancels the current recording and silences the reader.

The six record keys **toggle** — press once to start, press any record key again to
stop — so pick keys you can tap, not ones you hold.

Tips:
- **Avoid keys with strong OS defaults** when possible (`F5` = browser refresh,
  `F11` = fullscreen). The engine suppresses them while running, but a modifier combo
  like `ctrl+shift+<key>` is safest.
- The record keys (the 6 dictation/translate modes) must not collide with a modifier
  version of themselves — keep "action" keys on a different base key (that's why the
  defaults use `Shift+F1/F2/F3`, whose bare keys aren't record keys).

---

## 3. Choosing a Whisper model
Set `WHISPER_MODEL_NAME`. Larger = more accurate (Arabic gains the most) but slower
and more memory. Every model, with its size, memory, speed and accuracy, and which one
suits your PC: [docs/HARDWARE.md §4](docs/HARDWARE.md#speech-model--whisper_model_name).

A model you have not used before is downloaded from Hugging Face the next time the
engine starts (the console says so); after that it loads from the local cache with no
network call. No Hugging Face account or `HF_TOKEN` is needed. `WHISPER_MODEL_NAME`
also accepts the path to a local model folder. If a cached Whisper model folder lacks a
file (or has an empty one), the engine downloads the missing files at the pinned version.

**Where the models live.** The setting `MODELS_DIR`. Its default is the `HF_HOME`
environment variable if you have set it, otherwise `%LOCALAPPDATA%\ZeroFlow\models`.
Models are not downloaded again if `MODELS_DIR` points where they already are.

**Every model above is downloaded at a fixed version**, as are the built-in AI's
Gemma models and the reader's voice: `zeroflow/models.py` lists the exact Hugging Face
commit of each, so a fresh install never takes an upload nobody has checked. A model
you name yourself that is not in that list is taken at its latest version.

---

## 4. Changing the languages (e.g. Arabic → French)
The engine ships with **English + Arabic**, but Whisper `large-v3` understands ~99
languages, so you can swap Arabic (or English) for any of them. A language is just an
[ISO 639-1 code](https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes): `en` English,
`ar` Arabic, `fr` French, `es` Spanish, `de` German, `it` Italian, `pt` Portuguese,
`ru` Russian, `zh` Chinese, `ja` Japanese, `ko` Korean, `hi` Hindi, `tr` Turkish…

**Worked example — replace Arabic with French.** Make these edits, then restart:

1. **`zeroflow/engine.py` → `MODES`:** change each `"ar"` to `"fr"` and update the labels:
   ```python
   "ar_raw":    {"lang": "fr", "op": "raw",       "label": "FRENCH"},
   "ar_polish": {"lang": "fr", "op": "polish",    "label": "FRENCH · POLISH"},
   "en2ar":     {"lang": "en", "op": "translate", "to": "fr", "label": "TRANSLATE EN→FR"},
   "ar2en":     {"lang": "fr", "op": "translate", "to": "en", "label": "TRANSLATE FR→EN"},
   ```
   (The dict keys like `ar_raw` are just internal names — leave them, or rename them and
   also update the matching keys in `HOTKEYS` **and** the `HOTKEY_*` settings.)

2. **The Polish prompt.** `refine_text` uses `personas.ARABIC_POLISH_PROMPT` for `"ar"`
   and `personas.STANDARD_SYSTEM_PROMPT` for everything else — and that one says
   *answer in English only*, so French Polish would come back in English. Add a
   `FRENCH_POLISH_PROMPT` to `zeroflow/personas.py` (copy the Arabic one's shape) and pick it in
   `refine_text` for `"fr"`.

3. **`zeroflow/engine.py` → `refine_text`:** update the two display labels `"AR→EN"` / `"EN→AR"`
   to `"FR→EN"` / `"EN→FR"` (cosmetic only).

4. **`zeroflow/personas.py` → translate prompts:** edit the text to say *French* instead of *Arabic*:
   ```python
   TRANSLATE_TO_EN_PROMPT = "You are an elite French-to-English translation engine. ..."
   TRANSLATE_TO_AR_PROMPT = "You are an elite English-to-French translation engine. ..."
   ```
   (Keep the constant *names* — `refine_text` picks them by `to == "en"` vs. otherwise.)

5. *(Optional)* **`zeroflow/personas.py` → `VOICE_MACROS` / `PUNCTUATION_MAP`:** replace the Arabic
   spoken triggers (e.g. `"سطر جديد"`) with French ones (`"nouvelle ligne"`), and the
   Arabic punctuation rules with French equivalents.

Whisper already knows French, so **no model change is needed**. The same recipe works for
any language — or to go single-language, or to add a **third** language (add more entries
to `MODES` + `HOTKEYS` + the settings).

---

## 5. GPU vs CPU
By default (`"WHISPER_DEVICE": "auto"`) the engine tries CUDA first and **falls back to
the CPU (`int8`) automatically** if the CUDA libraries or the NVIDIA driver are missing
(`load_whisper_model` in `zeroflow/stt.py`).

```json
{
  "WHISPER_DEVICE": "auto",
  "WHISPER_COMPUTE_TYPE": "float16"
}
```
`WHISPER_DEVICE`: `auto` = NVIDIA GPU, falling back to CPU | `cpu` = skip the GPU.
`WHISPER_COMPUTE_TYPE` (GPU precision): `float16` | `int8_float16` | `int8`.

- **`"WHISPER_DEVICE": "cpu"`** skips the GPU attempt — the right setting when there is no
  NVIDIA card (AMD, Intel, built-in graphics), or to leave all the graphics memory to a
  big AI model.
- **`"WHISPER_COMPUTE_TYPE": "int8_float16"`** halves the speech model's graphics memory
  (large-v3 measured 3.9 GB → 2.0 GB) for about 0.2 s more per clip. Use it on cards
  under 11 GB. It only affects the GPU; the CPU always uses `int8`.
- The GPU needs the NVIDIA libraries and the CUDA build of `torch` (the voice); which
  packages each kind of PC installs: [INSTALL.md step 4](docs/INSTALL.md#4-install-the-python-packages).

Where the model ended up is shown in the start-up banner — e.g. `Speech to text:
[Whisper small · CPU · int8]` — and written to `flow_debug.log` (in `%LOCALAPPDATA%\ZeroFlow\logs`, see §9). Every dictation also
logs how long it took (`1.21s for 14.2s of audio`), which is the number to watch when
tuning.

If the CPU build of `torch` is installed on an NVIDIA PC, the reader still works — on
the CPU — and says so in `reader_debug.log` (§9). `READER_DEVICE` (§10) chooses the device
explicitly.

---

## 6. Choosing the AI provider
The AI model is only used for **Polish**, **Translate**, the **line-fix / maintenance**
actions and the reader's optional **Smart LLM Cleaning** — transcription itself is
always local Whisper. Both halves reach it through `zeroflow/llm`, which hands every
request to the provider named by `AI_PROVIDER` in `settings.json`:

| `AI_PROVIDER` | Talks to | Settings |
|---|---|---|
| `builtin` *(default)* | llama.cpp's `llama-server`, started and stopped by the engine itself, with Google's Gemma 4 E4B | `LLAMA_VARIANT`, `AI_BUILTIN_REPO`, `AI_BUILTIN_FILE` |
| `ollama` | a local Ollama server | `OLLAMA_HOST_URL`, `OLLAMA_MODEL_NAME`, `OLLAMA_KEEP_ALIVE` |
| `openai` | any server speaking the OpenAI `chat/completions` format — LM Studio, a llama.cpp server you run yourself, vLLM, or a cloud service such as OpenAI or Groq | `AI_URL`, `AI_MODEL`, and the API key in Credential Manager |
| `claude` | Anthropic's Claude, with your API key | `AI_MODEL`, and the API key in Credential Manager |

An unknown name is reported at start-up (in the window, the log and a pop-up) and Ollama
is used. Whatever the provider, an unreachable server, an error or an empty answer makes
Polish and Translate say **"AI unavailable"** and paste your own words.

### A) The built-in AI (default)
Nothing to run by hand: the engine starts `llama-server` as a hidden child process the
first time the AI is needed (at start-up, while Whisper loads), and it stops with the
engine — even after a crash. The reader uses the same server, so the model is in memory
once. Install the server once with `.\venv\Scripts\python.exe tools\get_llama.py`
([docs/INSTALL.md step 6](docs/INSTALL.md#6-install-the-built-in-ai)); the model downloads
from Hugging Face the first time the engine starts, then loads from the local cache.

```json
{
  "AI_PROVIDER": "builtin",
  "LLAMA_VARIANT": "auto",
  "AI_BUILTIN_REPO": "google/gemma-4-E4B-it-qat-q4_0-gguf",
  "AI_BUILTIN_FILE": "gemma-4-E4B_q4_0-it.gguf"
}
```
`LLAMA_VARIANT`: `auto` = from your graphics card: `cuda` (NVIDIA), `vulkan` (AMD Radeon /
Intel Arc — not tested yet), otherwise `cpu`. The AI's working memory is fixed at 8,192
tokens (a five-minute dictation and its answer), and it listens on the fixed local port
39281 (127.0.0.1, this PC only).

| Model | Download | When |
|---|---|---|
| Gemma 4 E4B (`google/gemma-4-E4B-it-qat-q4_0-gguf`, `gemma-4-E4B_q4_0-it.gguf`) | 5.15 GB | the default; English and Arabic tested |
| Gemma 4 E2B (`google/gemma-4-E2B-it-qat-q4_0-gguf`, `gemma-4-E2B_q4_0-it.gguf`) | 3.35 GB | `check_hardware.py` picks it for 4–5 GB laptop cards and 8 GB of RAM or less; its Arabic has not been tested yet |

Both are Google's own quantised builds, under the Apache 2.0 licence. Measured on an
RTX 4070 against Ollama: it loads in 3.1 s (Ollama 6.8–7.1 s), answers a Polish in
0.26 s (0.37 s) with the same English and Arabic, and holds about 3.2 GB of graphics
memory. If `runtime\llama\<build>\` is missing, the engine says so at start-up — naming
`tools/get_llama.py` — and uses Ollama instead. If the server stops while the engine
runs, the next request starts it again.

**Unload it when you do not need it.** Tray icon → **Unload AI model** frees its memory
(3.2 GB of graphics memory, measured); the next Polish or Translate loads it again by
itself, waiting about 4 s that once. `"AI_LOAD_AT_START": false` in `settings.json` keeps it
out of memory from the start, until the first Polish needs it.

### B) Ollama
```json
{
  "AI_PROVIDER": "ollama",
  "OLLAMA_MODEL_NAME": "qwen2.5:7b"
}
```
`OLLAMA_MODEL_NAME` is the name `ollama list` shows; blank = the first model Ollama serves.
If Ollama is down or serves no model, no model name is guessed and Polish says "AI
unavailable". Install Ollama from [ollama.com](https://ollama.com) and `ollama pull` the
model first.

### C) A local server you run (LM Studio, llama.cpp server, vLLM)
```json
{
  "AI_PROVIDER": "openai",
  "AI_URL": "http://localhost:1234/v1/chat/completions",
  "AI_MODEL": "your-model-id"
}
```
That address is LM Studio's; llama.cpp's server uses port 8080. `AI_MODEL` is the id as the
server names it.

### D) A cloud service with an API key
OpenAI, Groq, Together and others speak the OpenAI format:
```json
{
  "AI_PROVIDER": "openai",
  "AI_URL": "https://api.openai.com/v1/chat/completions",
  "AI_MODEL": "the-model-id"
}
```
**The API key is never in `settings.json`.** It lives in Windows Credential Manager, as a
generic credential named `ZeroFlow:<address>`. For `openai` the address is the scheme,
host and (non-default) port of `AI_URL`, so for the lines above it is
`ZeroFlow:https://api.openai.com`; for `claude` it is `ZeroFlow:https://api.anthropic.com`.
If your old `.env` held an `AI_API_KEY`, the first start moved it there and a start-up
notice said the old `.env` still holds the key: you can delete the `AI_API_KEY` line
there. To add or change a key by hand:
```powershell
cmdkey /generic:ZeroFlow:https://api.openai.com /user:ZeroFlow /pass
```
`cmdkey` then asks for the key. Leave `/pass` without a value: a key typed into the command
itself stays in PowerShell's saved history. (Or Control Panel → Credential Manager →
Windows Credentials → Add a generic credential, with that name.) Use the address of your
own server.

Anthropic's Claude has its own provider. Its package is not part of the main install;
add it once:
```powershell
.\venv\Scripts\python.exe -m pip install anthropic -c constraints.txt
```
then:
```json
{
  "AI_PROVIDER": "claude",
  "AI_MODEL": ""
}
```
`AI_MODEL` blank = `claude-opus-5-5`; `claude-sonnet-5-5` or `claude-haiku-5-5` cost less.
The key goes in Credential Manager as `ZeroFlow:https://api.anthropic.com`:
```powershell
cmdkey /generic:ZeroFlow:https://api.anthropic.com /user:ZeroFlow /pass
```
(It asks for the key; see above for why it is not typed into the command.)
With no key stored, Claude still works with the `ANTHROPIC_API_KEY` environment variable
or with `ant auth login`.

It answers a declined request on another model automatically, and reports a rejected
key, a model your key may not use, or a rate limit as a pop-up. Cloud round-trips are
slower than a local model.

### E) Anything else
Write a provider: a module in `zeroflow/llm/` with the three functions described in
`zeroflow/llm/base.py` — `ask(raw_text, context_text, instruction, timeout)` returning
the answer or `None`, `warm_up()`, and `model_name()`. `zeroflow/llm/openai_compatible.py`
is a complete example to copy (about 50 lines). Add it to `PROVIDERS` in
`zeroflow/llm/__init__.py`, then set `AI_PROVIDER` to its name.

> ⚠️ **Privacy:** with a **cloud** provider (`claude`, or `openai` pointed at a cloud
> service), the text you dictate is sent to that company's servers. Your clipboard is
> not: Polish's clipboard context goes only to an AI on this PC, unless you set
> `POLISH_CLIPBOARD_CONTEXT=on`. The built-in AI, Ollama, LM Studio and llama.cpp keep
> everything on your machine. Your API key lives only in Windows Credential Manager, never in `settings.json`.

---

## 7. Customizing the AI behavior (prompts)
All prompts live in **`zeroflow/personas.py`** — edit the strings to change how the LLM behaves.

| Constant | Controls |
|----------|----------|
| `STANDARD_SYSTEM_PROMPT` | how **English Polish** (F6) cleans text |
| `ARABIC_POLISH_PROMPT` | how **Arabic Polish** (F8) cleans text — into Modern Standard Arabic, fixing hamza, ة/ه and ى/ي, with Arabic punctuation |
| `ARABIC_WHISPER_HINT` | the sentence Whisper is primed with for Arabic dictation (F7/F8/F10) — keep it Arabic and punctuated |
| `TRANSLATE_TO_EN_PROMPT` / `TRANSLATE_TO_AR_PROMPT` | the two **Translate** directions |
| `LINE_CORRECTION_PROMPT` | the **fix line** action (Shift+F3) |
| `MEMORY_MAINTENANCE_PROMPT` | the **vocabulary janitor** (Shift+F1) |
| `READER_CLEANUP_PROMPT` | the reader's **Smart LLM Cleaning** before it speaks |

Example: to make Polish more aggressive, add a rule to `STANDARD_SYSTEM_PROMPT` like
"Rewrite run-on sentences into shorter ones."

**A language guard sits behind every prompt.** The key decides the language, so the
engine checks the answer: an Arabic answer must contain Arabic, an English one English,
and neither may contain Chinese, Japanese or Korean script. If the model answers in the
wrong language it pastes your own words instead, and `flow_debug.log` records that it
did (and what the model said, with `LOG_DICTATION_TEXT=True`). Arabic answers also lose any vowel marks the model adds unasked (tanween on
alif stays: *جدًا*). Some small models need this: `qwen2.5:7b` answered Arabic Polish in
Chinese in 5 tries out of 5 with the old prompt. Which models write the best Arabic:
[docs/HARDWARE.md §4](docs/HARDWARE.md#ai-model).

**Only the English prompt teaches words.** `[LEARN: …]` is in `STANDARD_SYSTEM_PROMPT`
alone, and a word is only learned if it appears in what you actually said — models
also "learn" words nobody said, and every learned word primes Whisper on each dictation.

---

## 8. Voice macros, punctuation & vocabulary
Also in **`zeroflow/personas.py`**:

- **`BASE_VOCABULARY`** — proper nouns / tech terms Whisper should spell correctly.
  Add your project names, tools, brands.
- **`VOICE_MACROS`** — spoken phrases that become keystrokes/formatting. Each entry is a
  list of trigger phrases (English **and** Arabic). Add your own:
  ```python
  VOICE_MACROS = {
      "new_line":   ["new line", "سطر جديد"],        # said first → Shift+Enter
      "bullet":     ["bullet", "point", "قائمة"],    # said first → "• " prefix
      "code_block": ["format code", "تنسيق كود"],    # said first → wrapped in `backticks`
  }
  ```
  They only count at the **start** of a dictation. Triggers match **whole words**,
  case-insensitively, and see past the punctuation Whisper adds ("New line. Hello"
  works). Because a trigger is a whole word, "Pointless" never becomes a bullet — but a
  sentence that really starts with "Point…" does, so drop `"point"` if that gets in
  your way.
- **`PUNCTUATION_MAP`** — trailing spoken punctuation → real punctuation (regex → mark).
  Each pattern is `_SPOKEN` (the spaces and marks Whisper puts in front of the word)
  plus the spoken word anchored at the end; Whisper's own closing mark is removed
  before matching. To add one:
  ```python
  r'(?i)' + _SPOKEN + r'exclamation (mark|point)$': '!',
  ```

---

## 9. Where your data lives
Your files are kept apart from the program folder, so an update never touches them.

| File | What | Managed |
|------|------|---------|
| `%APPDATA%\ZeroFlow\settings.json` | your settings (§1) | edited by hand; restart the engine after |
| `%APPDATA%\ZeroFlow\vocabulary.txt` | learned terms | deduped on write; `Shift+F1` prunes it |
| `%APPDATA%\ZeroFlow\vocabulary.txt.bak` | the list before the last `Shift+F1` | replaced each run — copy it back to undo |
| `%APPDATA%\ZeroFlow\history.md` | history of injected text | trimmed back past ~500 KB, after each write |
| `%LOCALAPPDATA%\ZeroFlow\logs\flow_debug.log` | dictation diagnostics — each dictation's size and timing, not its words (`LOG_DICTATION_TEXT`) | auto-rotates (~3 MB cap) |
| `%LOCALAPPDATA%\ZeroFlow\logs\reader_debug.log` | reader diagnostics | auto-rotates (~3 MB cap) |
| `%LOCALAPPDATA%\ZeroFlow\logs\flow_crash.log`, `reader_crash.log` | native crashes; normally empty | — |
| `%LOCALAPPDATA%\ZeroFlow\logs\builtin_ai.log` | the built-in AI's own output | appended; delete it any time |
| `MODELS_DIR`: `HF_HOME` if set, otherwise `%LOCALAPPDATA%\ZeroFlow\models` | the downloaded models (§3) | delete a model folder to free the space |
| Windows Credential Manager, `ZeroFlow:<address>` | your API key (§6 D) | — |

If you set `ZEROFLOW_SETTINGS` (developers), the settings file's folder holds the
vocabulary and the history instead. The old `.env`, `flow_vocabulary.txt` and
`flow_history.md` in the program folder are left as the first start found them and are
not read again.

`Shift+F2` clears the dictation log + history instantly. None of these grow without
bound. The reader keeps its own log (two processes cannot safely rotate one file);
it rotates itself and only writes a few lines per read.

---

## 10. The reader (text → speech)
Start it with **`Launch_Reader.bat`** (or `python -m reader`) on its own, or in the
same window as dictation with **`Launch_Zero.bat`** (recommended).

```json
{
  "HOTKEY_READ": "f4",
  "READER_VOICE": "af_heart",
  "READER_SMART_MODE": false
}
```
`READER_VOICE`: `af_heart` | `af_bella` | `bf_emma`. `READER_SMART_MODE`: `true` =
LLM-clean the capture before speaking.

`Esc` silences the reader as well as cancelling a recording.

**Tray menu.** Voice, **Smart LLM Cleaning** and **Suspend Reader** are all
switchable at runtime from the reader's tray icon; `settings.json` only sets the startup
defaults. The same menu holds **Exit Engine** (under `Launch_Zero.bat`, it stops both
halves) or **Exit Reader** (when the reader runs on its own).

**Smart mode.** Off by default. When on, the capture goes through the same local LLM
as Polish/Translate using `personas.READER_CLEANUP_PROMPT`, which strips navigation,
cookie notices and footnote markers. It never summarises, and if the LLM is slow,
unreachable, or the selection is longer than 1,000 characters (a fixed value), the
reader falls back to the instant regex clean — it never goes silent waiting for the model.

> **Cold-model note (Ollama only):** Ollama unloads an idle model after `OLLAMA_KEEP_ALIVE`. The first
> smart read after that spends its whole timeout (a fixed 10 seconds) waiting for the model
> to load and falls back to the regex clean; the next one is warm and works.

**Voices.** The three in the tray menu are the tested ones; `READER_VOICE` accepts any
voice id that Kokoro-82M ships. Each voice is a small file downloaded the first time it
is used and read from the local cache after that. To change the menu itself, edit
`VOICES` in `reader/voice_engine.py`.

**Pronunciation.** Words the voice mangles are rewritten phonetically just before
speaking, from `PRONUNCIATION_MAP` in `zeroflow/personas.py`:

```python
PRONUNCIATION_MAP = {
    "Yuki": "Yoo-kee",
    "Tsukihime": "Soo-kee-hee-may",
}
```

Keep these out of `BASE_VOCABULARY` — that list is a *spelling* hint for Whisper and
the casing pass, so a phonetic spelling there would corrupt your dictation.

**GPU.** `READER_DEVICE` picks the device for the voice model: `auto` (default — GPU
when available), `cpu`, or `cuda`.

This is honoured under every launcher, `Launch_Zero.bat` included: the reader always
runs in its own process, so it can hold CUDA without colliding with Whisper. (Host
both halves in a *single* process and that collision is a hard segfault — see
[ARCHITECTURE.md §12](ARCHITECTURE.md) — which is exactly why the engine spawns a
child process instead.)

Two numbers affect how quickly speech starts. They are fixed, measured values and no
longer settings: the first batch sent to the voice model is 120 characters (smaller would
start speech sooner but make more calls; the batch ends where a sentence ends — or, in a
first sentence longer than that, after a comma), and every batch after the first, once
audio is already playing, is 300.
