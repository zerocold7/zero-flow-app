# Configuration & Customization Guide

How to tweak Zero- Flow. Most things are changed in **`.env`** (no code). The deeper
ones (LLM provider, prompts, voice macros) are small, clearly-marked edits in the code.

> After changing **`.env`** you must **restart** the engine. Changes to `personas.py`
> or `local_flow.py` also require a restart.

---

## 1. `.env` quick reference
Copy `.env.example` to `.env` and edit. Everything here has a sensible default, so you
only set what you want to change.

| Variable | Default | What it does |
|----------|---------|--------------|
| `WHISPER_MODEL_NAME` | `large-v3` | Speech model — accuracy vs. speed/VRAM (see §3) |
| `OLLAMA_HOST_URL` | `http://127.0.0.1:11434/api/generate` | Where the LLM lives (see §6) |
| `FALLBACK_LLM` | `gemma2:27b` | Model name used if auto-discovery fails |
| `SAMPLE_RATE` | `16000` | Mic sample rate (Hz). Whisper expects 16000 — leave it |
| `CHANNELS` | `1` | Mic channels (mono). Leave it |
| `ENABLE_AUDIO_CHIMES` | `True` | Beeps on start/stop/success |
| `ENABLE_TOAST_NOTIFICATIONS` | `True` | Windows toast pop-ups |
| `HOTKEY_*` | see §2 | Key bindings |

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
HOTKEY_PANIC="esc"             # cancel the current recording
```

Tips:
- **Avoid keys with strong OS defaults** when possible (`F5` = browser refresh,
  `F11` = fullscreen). The engine suppresses them while running, but a modifier combo
  like `ctrl+shift+<key>` is safest.
- The record keys (the 6 dictation/translate modes) must not collide with a modifier
  version of themselves — keep "action" keys on a different base key (that's why the
  defaults use `Shift+F1/F2/F3`, whose bare keys aren't record keys).

---

## 3. Choosing a Whisper model
Set `WHISPER_MODEL_NAME`. Larger = more accurate but slower and more VRAM.

| Model | Rel. speed | ~VRAM (GPU) | Notes |
|-------|-----------|-------------|-------|
| `tiny` / `base` | fastest | ~1 GB | low accuracy, fine for quick English |
| `small` / `medium` | medium | ~2–5 GB | good balance |
| `large-v3` | slowest | ~5–6 GB | **default** — best accuracy, best Arabic |
| `distil-large-v3` | ~2× large | ~5 GB | near-large accuracy, faster (English-leaning) |

On CPU, prefer `small` or `medium` — `large-v3` is heavy without a GPU.

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
The engine tries CUDA (`float16`) first and **falls back to CPU (`int8`) automatically**
if the CUDA libraries are missing (`load_whisper_model` in `local_flow.py`).

- **GPU (NVIDIA):** keep `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` in
  `requirements.txt` (installed by default).
- **CPU-only:** remove those two lines to save ~1.2 GB. The engine will log
  `Whisper model active on CPU (int8)` at boot.

The chosen device is written to `flow_debug.log` at startup.

---

## 6. Using a different LLM provider (instead of Ollama)
The LLM is only used for **Polish**, **Translate**, and the **line-fix / maintenance**
actions — transcription itself is always local Whisper. The LLM integration is two
small functions in `local_flow.py`:

- `discover_ollama_model()` — asks Ollama which model is loaded (Ollama-specific).
- `query_ollama(raw_text, context_text, instruction)` — sends the request and returns
  the text.

To switch providers you edit `query_ollama` (and skip discovery). Below are drop-in
replacements.

### A) Any OpenAI-compatible server (LM Studio, llama.cpp, vLLM, OpenAI, Groq, Together…)
Most servers — local or cloud — speak the OpenAI `chat/completions` format. Add to `.env`:

```ini
OLLAMA_HOST_URL="http://localhost:1234/v1/chat/completions"   # your server's URL
FALLBACK_LLM="your-model-name"                                # exact model id
LLM_API_KEY=""                                                # required for cloud; blank for local
```

Then in `local_flow.py`, read the key near the other config:

```python
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
```

…and replace the request block inside `query_ollama` with:

```python
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {}
    response = requests.post(
        OLLAMA_HOST_URL,
        headers=headers,
        json={
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        },
        timeout=30.0,
    )
    ui.stop_processing_spinner()
    if response.status_code == 200:
        output = response.json()["choices"][0]["message"]["content"].strip()
        return _absorb_learned_word(output)
```

Finally, in `main()`, replace `OLLAMA_MODEL = discover_ollama_model()` with
`OLLAMA_MODEL = FALLBACK_LLM` (other providers don't have Ollama's `/api/tags`).

### B) Anthropic / Claude API
Same idea, different schema:

```ini
OLLAMA_HOST_URL="https://api.anthropic.com/v1/messages"
FALLBACK_LLM="claude-3-5-haiku-latest"
LLM_API_KEY="sk-ant-..."
```
```python
    response = requests.post(
        OLLAMA_HOST_URL,
        headers={"x-api-key": LLM_API_KEY, "anthropic-version": "2023-06-01"},
        json={
            "model": OLLAMA_MODEL,
            "max_tokens": 1024,
            "system": instruction,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        timeout=30.0,
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
      "new_line":   ["new line", "سطر جديد"],
      "bullet":     ["bullet", "point", "نقطة", "قائمة"],
      "code_block": ["format code", "كود"],
      "press_enter":["and send", "انتر"],
  }
  ```
- **`PUNCTUATION_MAP`** — trailing spoken punctuation → real punctuation (regex → char).

---

## 9. Where your data lives (all git-ignored)
| File | What | Managed |
|------|------|---------|
| `flow_vocabulary.txt` | learned terms | deduped on write; `Shift+F1` prunes it |
| `flow_history.md` | history of injected text | trimmed at boot past ~500 KB |
| `flow_debug.log` | diagnostics | auto-rotates (~3 MB cap) |
| `flow_capture.wav` | temp audio | deleted after each decode |

`Shift+F2` clears the log + history instantly. None of these grow without bound.
