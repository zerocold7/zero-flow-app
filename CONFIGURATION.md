# Configuration & Customization Guide

How to tweak Zero- Flow. Most things are changed in **`.env`** (no code). The deeper
ones (LLM provider, prompts, voice macros) are small, clearly-marked edits in the code.

One `.env` configures **both halves** — dictation (`local_flow.py`) and the reader
(`reader/`). Reader-only settings are in §10.

> After changing **`.env`** you must **restart** the engine. Changes to `personas.py`,
> `flow_core.py`, `local_flow.py` or `reader/` also require a restart.

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
| `OLLAMA_HOST_URL` | `http://127.0.0.1:11434/api/generate` | Where the LLM lives (see §6) |
| `OLLAMA_MODEL_NAME` | *(blank)* | Pin an exact model, e.g. `qwen2.5:7b`. Blank = auto-pick the first model Ollama serves |
| `FALLBACK_LLM` | `gemma2:27b` | Model name used only if Ollama is unreachable |
| `SAMPLE_RATE` | `16000` | Mic sample rate (Hz). Whisper expects 16000 — leave it |
| `CHANNELS` | `1` | Mic channels (mono). Leave it |
| `ENABLE_AUDIO_CHIMES` | `True` | Beeps on start/stop/success |
| `ENABLE_TOAST_NOTIFICATIONS` | `True` | Windows toast pop-ups |
| `HOTKEY_*` | see §2 | Key bindings |
| `HOTKEY_READ` | `f4` | Read the highlighted text aloud (see §10) |
| `READER_VOICE` | `af_heart` | Which Kokoro voice speaks (see §10) |
| `READER_SMART_MODE` | `False` | LLM-clean captured text before speaking (see §10) |
| `READER_SMART_MAX_CHARS` | `1000` | Selections longer than this skip the LLM pass |
| `READER_LLM_TIMEOUT` | `10` | Seconds to wait for the LLM before speaking anyway |
| `READER_DEVICE` | `auto` | `auto` / `cpu` / `cuda` for the voice model (see §10) |
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

Bold figures were measured on an RTX 4070; the rest are estimates from model size. On
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

1. **`local_flow.py` → `MODES`:** change each `"ar"` to `"fr"` and update the labels:
   ```python
   "ar_raw":    {"lang": "fr", "op": "raw",       "label": "FRENCH"},
   "ar_polish": {"lang": "fr", "op": "polish",    "label": "FRENCH · POLISH"},
   "en2ar":     {"lang": "en", "op": "translate", "to": "fr", "label": "TRANSLATE EN→FR"},
   "ar2en":     {"lang": "fr", "op": "translate", "to": "en", "label": "TRANSLATE FR→EN"},
   ```
   (The dict keys like `ar_raw` are just internal names — leave them, or rename them and
   also update the matching keys in `HOTKEYS` **and** the `HOTKEY_*` lines in `.env`.)

2. **`local_flow.py` → `SUPPORTED_LANGS`:** `("ar", "en")` → `("fr", "en")`.

3. **`local_flow.py` → `refine_text`:** update the two display labels `"AR→EN"` / `"EN→AR"`
   to `"FR→EN"` / `"EN→FR"` (cosmetic only).

4. **`personas.py` → translate prompts:** edit the text to say *French* instead of *Arabic*:
   ```python
   TRANSLATE_TO_EN_PROMPT = "You are an elite French-to-English translation engine. ..."
   TRANSLATE_TO_AR_PROMPT = "You are an elite English-to-French translation engine. ..."
   ```
   (Keep the constant *names* — `refine_text` picks them by `to == "en"` vs. otherwise.)

5. *(Optional)* **`personas.py` → `VOICE_MACROS` / `PUNCTUATION_MAP`:** replace the Arabic
   spoken triggers (e.g. `"سطر جديد"`) with French ones (`"nouvelle ligne"`), and the
   Arabic punctuation rules with French equivalents.

Whisper already knows French, so **no model change is needed**. The same recipe works for
any language — or to go single-language, or to add a **third** language (add more entries
to `MODES` + `HOTKEYS` + `.env`).

---

## 5. GPU vs CPU
By default (`WHISPER_DEVICE="auto"`) the engine tries CUDA first and **falls back to
the CPU (`int8`) automatically** if the CUDA libraries or the NVIDIA driver are missing
(`load_whisper_model` in `local_flow.py`).

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
`pip install -r requirements.txt` alone fetches the CPU-only build. On an NVIDIA
machine, install it first:

```bash
pip install torch==2.5.1+cu121 --index-url https://download.pytorch.org/whl/cu121
```

If the CPU build is installed anyway, the reader still works — on the CPU — and says so
in `reader_debug.log`. `READER_DEVICE` (§10) chooses the device explicitly.

---

## 6. Using a different LLM provider (instead of Ollama)
The LLM is only used for **Polish**, **Translate**, the **line-fix / maintenance**
actions and the reader's optional **Smart LLM Cleaning** — transcription itself is
always local Whisper. Both halves reach the LLM through two functions in
**`flow_core.py`**:

- `discover_ollama_model()` — picks the model: `OLLAMA_MODEL_NAME` if set, otherwise
  whatever Ollama serves first. **Setting `OLLAMA_MODEL_NAME` skips the Ollama-only
  discovery entirely**, which is all another provider needs here.
- `query_ollama(raw_text, context_text, instruction, timeout=15.0)` — sends the request
  and returns the text (or the input unchanged if anything fails).

To switch providers you replace the body of `query_ollama`. The function keeps its
name, so nothing else changes.

### A) Any OpenAI-compatible server (LM Studio, llama.cpp, vLLM, OpenAI, Groq, Together…)
Most servers — local or cloud — speak the OpenAI `chat/completions` format. In `.env`:

```ini
OLLAMA_HOST_URL="http://localhost:1234/v1/chat/completions"   # your server's URL
OLLAMA_MODEL_NAME="your-model-id"                             # exact model id
LLM_API_KEY=""                                                # required for cloud; blank for local
```

In `flow_core.py`, read the key next to the other configuration:

```python
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
```

…and replace `query_ollama` with:

```python
def query_ollama(raw_text, context_text, instruction, timeout=15.0):
    user = f"Context Window Data:\n{context_text}\n\n" if context_text else ""
    user += f"Input Raw String: {raw_text}\nOutput String:"

    ui.start_processing_spinner("AI Processing")
    try:
        headers = {"Authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {}
        response = requests.post(
            OLLAMA_HOST_URL,
            headers=headers,
            json={
                "model": get_ollama_model(),
                "messages": [
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
            },
            timeout=timeout,
        )
        ui.stop_processing_spinner()
        if response.status_code == 200:
            output = response.json()["choices"][0]["message"]["content"].strip()
            return _absorb_learned_word(output)
        logging.warning(f"LLM returned HTTP {response.status_code}: {response.text[:200]}")
        ui.show_toast("⚠️ LLM Error", f"HTTP {response.status_code}.", ENABLE_TOASTS)
    except Exception as e:
        ui.stop_processing_spinner()
        logging.warning(f"LLM request failed: {e}")
        ui.show_toast("⚠️ LLM Offline", "The LLM API failed to respond.", ENABLE_TOASTS)
    return raw_text
```

Cloud round-trips are slower than a local model; if replies time out, raise the
`timeout=15.0` default (the reader passes its own `READER_LLM_TIMEOUT`).

### B) Anthropic / Claude API
Same shape, different request and response. In `.env`:

```ini
OLLAMA_HOST_URL="https://api.anthropic.com/v1/messages"
OLLAMA_MODEL_NAME="claude-haiku-4-5-20251001"   # fast and inexpensive, suits clean-up work
LLM_API_KEY="sk-ant-..."
```

In the function above, replace the `requests.post(...)` call and the success branch:

```python
        response = requests.post(
            OLLAMA_HOST_URL,
            headers={"x-api-key": LLM_API_KEY, "anthropic-version": "2023-06-01"},
            json={
                "model": get_ollama_model(),
                "max_tokens": 1024,
                "system": instruction,
                "messages": [{"role": "user", "content": user}],
                "temperature": 0.2,
            },
            timeout=timeout,
        )
        ui.stop_processing_spinner()
        if response.status_code == 200:
            output = response.json()["content"][0]["text"].strip()
            return _absorb_learned_word(output)
```

> ⚠️ **Privacy:** with a **cloud** provider, the text you dictate (and clipboard
> context in Polish mode) is sent to that company's servers. Local servers (Ollama,
> LM Studio, llama.cpp) keep everything on your machine. Your `LLM_API_KEY` lives only
> in `.env`, which is git-ignored.

---

## 7. Customizing the AI behavior (prompts)
All prompts live in **`personas.py`** — edit the strings to change how the LLM behaves.

| Constant | Controls |
|----------|----------|
| `STANDARD_SYSTEM_PROMPT` | how **Polish** (F6/F8) cleans text |
| `TRANSLATE_TO_EN_PROMPT` / `TRANSLATE_TO_AR_PROMPT` | the two **Translate** directions |
| `LINE_CORRECTION_PROMPT` | the **fix line** action (Shift+F3) |
| `MEMORY_MAINTENANCE_PROMPT` | the **vocabulary janitor** (Shift+F1) |
| `READER_CLEANUP_PROMPT` | the reader's **Smart LLM Cleaning** before it speaks |

Example: to make Polish more aggressive, add a rule to `STANDARD_SYSTEM_PROMPT` like
"Rewrite run-on sentences into shorter ones."

---

## 8. Voice macros, punctuation & vocabulary
Also in **`personas.py`**:

- **`BASE_VOCABULARY`** — proper nouns / tech terms Whisper should spell correctly.
  Add your project names, tools, brands.
- **`VOICE_MACROS`** — spoken phrases that become keystrokes/formatting. Each entry is a
  list of trigger phrases (English **and** Arabic). Add your own:
  ```python
  VOICE_MACROS = {
      "new_line":   ["new line", "سطر جديد"],        # said first → Shift+Enter
      "bullet":     ["bullet", "point", "نقطة", "قائمة"],  # said first → "• " prefix
      "code_block": ["format code", "كود"],          # said first → wrapped in `backticks`
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
| `flow_history.md` | history of injected text | trimmed at boot past ~500 KB |
| `flow_debug.log` | dictation diagnostics | auto-rotates (~3 MB cap) |
| `reader_debug.log` | reader diagnostics | auto-rotates (~3 MB cap) |
| `flow_capture.wav` | temp audio | deleted after each decode |

`Shift+F2` clears the dictation log + history instantly. None of these grow without
bound. The reader keeps its own log (two processes cannot safely rotate one file);
it rotates itself and only writes a few lines per read.

---

## 10. The reader (text → speech)
Start it with **`Launch_Reader.bat`** (or `python -m reader`) on its own, alongside
dictation in a second window with **`Launch_All.bat`**, or in the same window as
dictation with **`Launch_Zero.bat`** (recommended).

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

> **Cold-model note:** Ollama unloads an idle model after a few minutes. The first
> smart read after that spends its whole timeout waiting for the model to load and
> falls back to the regex clean; the next one is warm and works. Raise
> `READER_LLM_TIMEOUT` if you would rather wait than fall back.

**Voices.** The three in the tray menu are the tested ones; `READER_VOICE` accepts any
voice id that Kokoro-82M ships. Each voice is a small file downloaded the first time it
is used and read from the local cache after that. To change the menu itself, edit
`VOICES` in `reader/voice_engine.py`.

**Pronunciation.** Words the voice mangles are rewritten phonetically just before
speaking, from `PRONUNCIATION_MAP` in `personas.py`:

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
