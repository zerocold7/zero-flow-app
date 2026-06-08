# Zero- Flow — Architecture & Behaviour Guide

A practical map of what the engine does, how it should behave, and where each piece
lives in the code. Read this before changing `local_flow.py`.

---

## 1. What it is
A background Windows process that turns speech into typed text in whatever app has
focus. You hold a hotkey, talk, release — the words appear at your cursor. It is
**bilingual (Arabic / English)**, runs **fully locally** (no cloud), and can optionally
clean up or translate the text with a local LLM.

Three source files:

| File | Responsibility |
|------|----------------|
| `local_flow.py` | The engine: config, hotkeys, audio, transcription, refinement, injection |
| `personas.py`   | Static data: LLM prompts, base vocabulary, voice macros, punctuation map |
| `engine_ui.py`  | Console UI, beeps, Windows toasts, system-tray + window icon |

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

| Hotkey | Mode | Behaviour |
|--------|------|-----------|
| `F9`  | `raw`       | Transcribe and inject exactly as spoken (no LLM) |
| `F8`  | `english`   | Same as raw, but **forces English** (skips language auto-detect) |
| `F10` | `polish`    | Transcribe, then LLM cleans grammar/fillers **in the same language** |
| `F11` | `translate` | Transcribe, then LLM translates **Arabic⇄English** (direction auto-detected) |
| `Ctrl+F10` | line fix  | Select the current line, fix typos via the LLM, paste back |
| `Ctrl+F11` | maintenance | LLM dedupes/cleans the learned-vocabulary file |
| `Esc` | cancel | Cancels an in-progress recording **only** (does nothing when idle) |

All record keys are registered with `suppress=True` so they never leak into the
focused app (otherwise `F11` would toggle browser fullscreen, `F10` open menus, etc.).
`Esc` is intentionally **not** suppressed, so it keeps working normally everywhere.

While recording, pressing **any** record key **stops** the capture — it never switches
mode. (Mid-recording switching used to cause accidental translations.)

---

## 4. Language handling (the bilingual core)
- In every mode except `english`, Whisper **auto-detects** the spoken language, so
  Arabic stays Arabic and English stays English.
- The engine only supports `ar` and `en` (`SUPPORTED_LANGS`). If auto-detect returns
  any other language — a misdetection that produces gibberish (e.g. Malay/Hebrew on a
  noisy clip) — `transcribe_clip` **re-decodes**, forcing whichever of Arabic/English
  scored higher in `all_language_probs`. Output is therefore never a third language.
- `F8` (english) bypasses all of this and forces `language="en"`.
- The Whisper hint (`initial_prompt`) is **only the vocabulary term list** — never an
  English sentence, which would bias the decoder into writing Arabic as English.

For Translate mode, the detected language picks the direction:
`ar → TRANSLATE_TO_EN_PROMPT`, anything else `→ TRANSLATE_TO_AR_PROMPT`.

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
- At boot the engine queries Ollama's `/api/tags` and binds to the **first model it is
  serving** — no hardcoded model. If Ollama is unreachable it uses `FALLBACK_LLM`.
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
- **Punctuation map**: trailing spoken punctuation ("period", "comma", Arabic
  equivalents) becomes real punctuation.
- **Vocabulary casing**: known terms are re-cased to their canonical form.
- Injection is done by saving the clipboard, pasting via `Ctrl+V`, then **restoring**
  the original clipboard.

---

## 9. Files written at runtime (git-ignored)
| File | Purpose |
|------|---------|
| `flow_capture.wav` | Temporary audio buffer (deleted after each decode) |
| `flow_vocabulary.txt` | Learned proper nouns / tech terms |
| `flow_history.md` | Append-only log of injected text |
| `flow_debug.log` | Diagnostics: device, detected language, mode, transcription result, errors |

The debug log is the first place to look when something misbehaves — every transcription
records `mode=…` and `lang=…`, and re-decodes / skips / fallbacks are all logged.
