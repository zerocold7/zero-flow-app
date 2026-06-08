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
| `flow_vocabulary.txt` | Learned proper nouns / tech terms (deduped on write, pruned by `Shift+F1`) |
| `flow_history.md` | Append-only log of injected text; auto-trimmed at boot past ~500 KB |
| `flow_debug.log` | Diagnostics; auto-rotated at ~1 MB (×2 backups ≈ 3 MB cap) |

**None of these grow without bound:** the debug log rotates, history is trimmed at boot,
and `Shift+F2` clears both on demand. The debug log is the first place to look when
something misbehaves — every transcription records `mode=…` and `lang=…`, and
re-decodes / skips / fallbacks are all logged.
