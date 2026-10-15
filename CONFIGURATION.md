# Configuration & Customization Guide

How to tweak Zero- Flow. Most things are changed in **`.env`** (no code). The deeper
ones (LLM provider, prompts, voice macros) are small, clearly-marked edits in the code.

One `.env` configures **both halves** — dictation (`zeroflow/engine.py`) and the reader
(`reader/`). Reader-only settings are in §10.

> After changing **`.env`** you must **restart** the engine. Changes to the code
> (`zeroflow/`, `reader/`) also require a restart.

---

## 1. `.env` quick reference
Copy `.env.example` to `.env` and edit. Everything here has a sensible default, so you
only set what you want to change.

> **The hardware-dependent settings have a shortcut.** `python check_hardware.py
> --apply` detects your PC and writes the model and device settings for it; `presets/`
> holds the same values as one file per kind of hardware. What each tier means, with
> measured speeds: [docs/HARDWARE.md](docs/HARDWARE.md).

| Variable | Default | What it does |
|----------|---------|--------------|
| `WHISPER_MODEL_NAME` | `large-v3` | Speech model — accuracy vs. speed/VRAM (see §3) |
| `WHISPER_DEVICE` | `auto` | `auto` = NVIDIA GPU, falling back to CPU · `cpu` = skip the GPU (see §5) |
| `WHISPER_COMPUTE_TYPE` | `float16` | GPU precision; `int8_float16` halves graphics memory (see §5) |
| `AI_PROVIDER` | `builtin` | Which AI runs Polish and Translate: `builtin` (inside the engine), `ollama`, `openai` (any server speaking the OpenAI chat format) or `claude` (see §6) |
| `LLAMA_VARIANT` | `auto` | The built-in AI's build: `auto` (from the graphics card), `cuda`, `vulkan` or `cpu` |
| `AI_BUILTIN_REPO` / `AI_BUILTIN_FILE` | Gemma 4 E4B | The built-in AI's model on Hugging Face (Gemma 4 E2B is smaller — see §6) |
| `AI_NUM_CTX` | `8192` | The built-in AI's working memory, in tokens |
| `AI_BUILTIN_PORT` | `39281` | The local port the built-in AI listens on (this PC only) |
| `AI_URL` / `AI_MODEL` / `AI_API_KEY` | *(blank)* | For `openai` and `claude` (see §6) |
| `OLLAMA_HOST_URL` | `http://127.0.0.1:11434/api/generate` | `ollama` only: where Ollama listens |
| `OLLAMA_MODEL_NAME` | *(blank)* | `ollama` only: pin an exact model, e.g. `qwen2.5:7b`. Blank = auto-pick the first model Ollama serves |
| `FALLBACK_LLM` | `gemma2:27b` | `ollama` only: model name used if Ollama is unreachable |
| `MAX_RECORDING_SECONDS` | `300` | A recording left running stops by itself after this many seconds, and is transcribed as usual |
| `ENABLE_AUDIO_CHIMES` | `True` | Beeps on start/stop/success |
| `ENABLE_TOAST_NOTIFICATIONS` | `True` | Windows toast pop-ups |
| `HOTKEY_*` | see §2 | Key bindings |
| `HOTKEY_READ` | `f4` | Read the highlighted text aloud (see §10) |
| `READER_VOICE` | `af_heart` | Which Kokoro voice speaks (see §10) |
| `READER_SMART_MODE` | `False` | LLM-clean captured text before speaking (see §10) |
| `READER_SMART_MAX_CHARS` | `1000` | Selections longer than this skip the LLM pass |
| `READER_LLM_TIMEOUT` | `10` | Seconds to wait for the LLM before speaking anyway |
| `READER_DEVICE` | `auto` | `auto` / `cpu` / `cuda` for the voice model (see §10) |
| `OLLAMA_KEEP_ALIVE` | `30m` | `ollama` only: how long the AI model stays loaded after use. The engine also loads it at start-up, so the first Polish is instant. `0` unloads at once (frees memory) |
| `OLLAMA_NUM_CTX` | `8192` | `ollama` only: the AI model's working memory, in tokens. Enough for a five-minute dictation and its answer; gemma4-e4b's own setting (131,072) held 0.6 GB more graphics memory for nothing. `0` keeps the model's own |
| `READER_FIRST_BATCH_CHARS` | `120` | Size of the first chunk of text sent to the voice (see §10) |
| `READER_BATCH_CHARS` | `300` | Size of every chunk after the first (see §10) |

---

## 2. Changing hotkeys
Each binding is a `HOTKEY_*` line in `.env`. The value is a key name in
[`keyboard`](https://github.com/boppreh/keyboard) syntax: `f5`, `ctrl+shift+d`,
`alt+space`, `print screen`, etc.

```ini
HOTKEY_EN_RAW="f5"          # English, raw
HOTKEY_EN_POLISH="f6"       # English, AI cleanup
HOTKEY_AR_RAW="f7"          # Arabic, raw
HOTKEY_AR_POLISH="f8"       # Arabic, AI cleanup
HOTKEY_EN2AR="f9"           # Translate English -> Arabic
HOTKEY_AR2EN="f10"          # Translate Arabic -> English
HOTKEY_FIX="shift+f3"          # fix the current line
HOTKEY_MAINTENANCE="shift+f1"  # vocabulary maintenance
HOTKEY_PURGE="shift+f2"        # clear debug log & history
HOTKEY_PANIC="esc"             # cancel the current recording / silence the reader
HOTKEY_READ="f4"               # read the highlighted text aloud (reader)
```

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
and more memory.

| Model | Download | GPU memory (`float16` / `int8_float16`) | Notes |
|-------|----------|------------------------------------------|-------|
| `tiny` / `base` | 75 / 145 MB | ≈0.2–0.3 GB / less | fastest, low accuracy, weak Arabic |
| `small` | 480 MB | ≈0.7 / 0.35 GB | the CPU default — good English, fair Arabic |
| `medium` | 1.5 GB | ≈2 / 1 GB | good balance; the NVIDIA-laptop default |
| `large-v3` | 3 GB | **3.9 / 2.0 GB** | **default** — best accuracy, best Arabic |
| `distil-large-v3` | 1.5 GB | ≈2 / 1 GB | faster large-quality — **English only**, useless for the Arabic keys |
| `mobiuslabsgmbh/faster-whisper-large-v3-turbo` | 1.6 GB | — | **English as accurate as `large-v3` and 35% faster** (0.29 vs 0.46 s per clip); **Arabic much worse** (56% vs 35% character errors). Only for English-only use |

Bold figures were measured on an RTX 4070 (the turbo comparison with
`tools/bench/bench_stt.py`, on synthetic clips); the rest are estimates from model size. On
a CPU, `large-v3` took 12.8 s for a 14 s clip — prefer `small`. The full per-hardware
picture, with measured speeds: [docs/HARDWARE.md](docs/HARDWARE.md).

A model you have not used before is downloaded from Hugging Face the next time the
engine starts (the console says so); after that it loads from the local cache with no
network call. No Hugging Face account or `HF_TOKEN` is needed. `WHISPER_MODEL_NAME`
also accepts the path to a local model folder.

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
   also update the matching keys in `HOTKEYS` **and** the `HOTKEY_*` lines in `.env`.)

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
to `MODES` + `HOTKEYS` + `.env`).

---

## 5. GPU vs CPU
By default (`WHISPER_DEVICE="auto"`) the engine tries CUDA first and **falls back to
the CPU (`int8`) automatically** if the CUDA libraries or the NVIDIA driver are missing
(`load_whisper_model` in `zeroflow/stt.py`).

```ini
WHISPER_DEVICE="auto"             # auto = NVIDIA GPU, falling back to CPU | cpu = skip the GPU
WHISPER_COMPUTE_TYPE="float16"    # GPU precision: float16 | int8_float16 | int8
```

- **`WHISPER_DEVICE="cpu"`** skips the GPU attempt — the right setting when there is no
  NVIDIA card (AMD, Intel, built-in graphics), or to leave all the graphics memory to a
  big AI model.
- **`WHISPER_COMPUTE_TYPE="int8_float16"`** halves the speech model's graphics memory
  (large-v3 measured 3.9 GB → 2.0 GB) for about 0.2 s more per clip. Use it on cards
  under 11 GB. It only affects the GPU; the CPU always uses `int8`.
- **GPU (NVIDIA):** keep `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` in
  `requirements.txt` (installed by default).
- **CPU-only:** remove those two lines to save ~1.2 GB.

Where the model ended up is shown in the start-up banner — e.g. `Speech to text:
[Whisper small · CPU · int8]` — and written to `flow_debug.log`. Every dictation also
logs how long it took (`1.21s for 14.2s of audio`), which is the number to watch when
tuning.

The **voice model** (reader) needs the CUDA build of `torch` for the GPU, and
`pip install -r requirements.txt -c constraints.txt` alone fetches the CPU-only build.
(`constraints.txt` pins every package underneath to a set known to work together; see
[INSTALL.md](docs/INSTALL.md).) On an NVIDIA machine, install it first:

```bash
pip install torch==2.5.1+cu121 --index-url https://download.pytorch.org/whl/cu121
```

If the CPU build is installed anyway, the reader still works — on the CPU — and says so
in `reader_debug.log`. `READER_DEVICE` (§10) chooses the device explicitly.

---

## 6. Choosing the AI provider
The AI model is only used for **Polish**, **Translate**, the **line-fix / maintenance**
actions and the reader's optional **Smart LLM Cleaning** — transcription itself is
always local Whisper. Both halves reach it through `zeroflow/llm`, which hands every
request to the provider named by `AI_PROVIDER` in `.env`:

| `AI_PROVIDER` | Talks to | Settings |
|---|---|---|
| `builtin` *(default)* | llama.cpp's `llama-server`, started and stopped by the engine itself, with Google's Gemma 4 E4B | `LLAMA_VARIANT`, `AI_BUILTIN_REPO`, `AI_BUILTIN_FILE`, `AI_NUM_CTX`, `AI_BUILTIN_PORT` |
| `ollama` | a local Ollama server | `OLLAMA_HOST_URL`, `OLLAMA_MODEL_NAME`, `FALLBACK_LLM`, `OLLAMA_KEEP_ALIVE`, `OLLAMA_NUM_CTX` |
| `openai` | any server speaking the OpenAI `chat/completions` format — LM Studio, a llama.cpp server you run yourself, vLLM, or a cloud service such as OpenAI or Groq | `AI_URL`, `AI_MODEL`, `AI_API_KEY` |
| `claude` | Anthropic's Claude, with your API key | `AI_API_KEY`, `AI_MODEL` |

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

```ini
AI_PROVIDER="builtin"
LLAMA_VARIANT="auto"     # auto = from your graphics card: cuda (NVIDIA), vulkan (AMD Radeon /
                         # Intel Arc — not tested yet), otherwise cpu
AI_BUILTIN_REPO="google/gemma-4-E4B-it-qat-q4_0-gguf"
AI_BUILTIN_FILE="gemma-4-E4B_q4_0-it.gguf"
AI_NUM_CTX=8192          # working memory in tokens: a five-minute dictation and its answer
AI_BUILTIN_PORT=39281    # the local port it listens on (127.0.0.1, this PC only)
```

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

### B) Ollama
```ini
AI_PROVIDER="ollama"
OLLAMA_MODEL_NAME="qwen2.5:7b"    # as `ollama list` names it; blank = the first one Ollama serves
```
Install Ollama from [ollama.com](https://ollama.com) and `ollama pull` the model first.

### C) A local server you run (LM Studio, llama.cpp server, vLLM)
```ini
AI_PROVIDER="openai"
AI_URL="http://localhost:1234/v1/chat/completions"   # LM Studio; llama.cpp's server uses port 8080
AI_MODEL="your-model-id"                             # as the server names it
```

### D) A cloud service with an API key
OpenAI, Groq, Together and others speak the OpenAI format:
```ini
AI_PROVIDER="openai"
AI_URL="https://api.openai.com/v1/chat/completions"
AI_MODEL="the-model-id"
AI_API_KEY="sk-..."
```
Anthropic's Claude has its own provider:
```ini
AI_PROVIDER="claude"
AI_API_KEY="sk-ant-..."    # blank = the key in ANTHROPIC_API_KEY
AI_MODEL=""                # blank = claude-opus-5-5; claude-sonnet-5-5 or claude-haiku-5-5 cost less
```
It answers a declined request on another model automatically, and reports a rejected
key, a model your key may not use, or a rate limit as a pop-up. Cloud round-trips are
slower than a local model. (The app window, phase 5, will keep the key in Windows
Credential Manager instead of `.env`.)

### E) Anything else
Write a provider: a module in `zeroflow/llm/` with the three functions described in
`zeroflow/llm/base.py` — `ask(raw_text, context_text, instruction, timeout)` returning
the answer or `None`, `warm_up()`, and `model_name()`. `zeroflow/llm/openai_compatible.py`
is a complete example to copy (about 50 lines). Add it to `PROVIDERS` in
`zeroflow/llm/__init__.py`, then set `AI_PROVIDER` to its name.

> ⚠️ **Privacy:** with a **cloud** provider (`claude`, or `openai` pointed at a cloud
> service), the text you dictate (and clipboard context in Polish mode) is sent to that
> company's servers. The built-in AI, Ollama, LM Studio and llama.cpp keep everything on
> your machine. Your `AI_API_KEY` lives only in `.env`, which is git-ignored.

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
wrong language it pastes your own words instead, and `flow_debug.log` records what the
model said. Arabic answers also lose any vowel marks the model adds unasked (tanween on
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
      "press_enter":["and send", "انتر"],            # said last  → Enter after pasting
  }
  ```
  The first three only count at the **start** of a dictation and `press_enter` only
  at the **end**. Triggers match **whole words**, case-insensitively, and see past the
  punctuation Whisper adds ("New line. Hello" and "…see you then, and send." both
  work). Because a trigger is a whole word, "Pointless" never becomes a bullet — but a
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

## 9. Where your data lives (all git-ignored)
| File | What | Managed |
|------|------|---------|
| `flow_vocabulary.txt` | learned terms | deduped on write; `Shift+F1` prunes it |
| `flow_vocabulary.txt.bak` | the list before the last `Shift+F1` | replaced each run — copy it back to undo |
| `flow_history.md` | history of injected text | trimmed back past ~500 KB, after each write |
| `flow_debug.log` | dictation diagnostics | auto-rotates (~3 MB cap) |
| `reader_debug.log` | reader diagnostics | auto-rotates (~3 MB cap) |
| `builtin_ai.log` | the built-in AI's own output | appended; delete it any time |

`Shift+F2` clears the dictation log + history instantly. None of these grow without
bound. The reader keeps its own log (two processes cannot safely rotate one file);
it rotates itself and only writes a few lines per read.

---

## 10. The reader (text → speech)
Start it with **`Launch_Reader.bat`** (or `python -m reader`) on its own, or in the
same window as dictation with **`Launch_Zero.bat`** (recommended).

```ini
HOTKEY_READ="f4"            # read the highlighted text aloud
READER_VOICE="af_heart"     # af_heart | af_bella | bf_emma
READER_SMART_MODE="False"   # True = LLM-clean the capture before speaking
READER_SMART_MAX_CHARS=1000 # longer selections skip the LLM pass
READER_LLM_TIMEOUT=10       # seconds to wait before speaking anyway
```

`HOTKEY_PANIC` (default `Esc`) silences the reader as well as cancelling a recording.

**Tray menu.** Voice, **Smart LLM Cleaning** and **Suspend Reader** are all
switchable at runtime from the reader's tray icon; `.env` only sets the startup
defaults. The same menu holds **Exit Engine** (under `Launch_Zero.bat`, it stops both
halves) or **Exit Reader** (when the reader runs on its own).

**Smart mode.** Off by default. When on, the capture goes through the same local LLM
as Polish/Translate using `personas.READER_CLEANUP_PROMPT`, which strips navigation,
cookie notices and footnote markers. It never summarises, and if the LLM is slow,
unreachable, or the selection is longer than `READER_SMART_MAX_CHARS`, the reader
falls back to the instant regex clean — it never goes silent waiting for the model.

> **Cold-model note (Ollama only):** Ollama unloads an idle model after `OLLAMA_KEEP_ALIVE`. The first
> smart read after that spends its whole timeout waiting for the model to load and
> falls back to the regex clean; the next one is warm and works. Raise
> `READER_LLM_TIMEOUT` if you would rather wait than fall back.

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

Two knobs affect how quickly speech starts, both rarely worth changing:

| Variable | Default | What it does |
|----------|---------|--------------|
| `READER_FIRST_BATCH_CHARS` | `120` | Size of the first batch sent to the voice model. Smaller = speech starts sooner, but more calls |
| `READER_BATCH_CHARS` | `300` | Size of every batch after the first, once audio is already playing |
