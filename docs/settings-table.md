# Settings table (draft for approval, Phase 5a → 5b)

Every setting in `zeroflow/settings.py`, and where each one goes in the Settings window.
**Main** = the main tabs. **Advanced** = the Advanced tab. **Fixed** = becomes a constant in the code and leaves the settings file.
New settings that 5b brings are listed at the end. Terms as in `CONTEXT.md`.

## Keys

| Setting today | Default | Goes to | Shown as |
|---|---|---|---|
| `HOTKEY_EN_RAW` | F5 | Main | Raw · English |
| `HOTKEY_EN_POLISH` | F6 | Main | Polish · English |
| `HOTKEY_AR_RAW` | F7 | Main | Raw · Arabic |
| `HOTKEY_AR_POLISH` | F8 | Main | Polish · Arabic |
| `HOTKEY_EN2AR` | F9 | Main | Translate · English → Arabic |
| `HOTKEY_AR2EN` | F10 | Main | Translate · Arabic → English |
| `HOTKEY_FIX` | Shift+F3 | Main | Action · Fix line |
| `HOTKEY_MAINTENANCE` | Shift+F1 | Main | Action · Tidy vocabulary |
| `HOTKEY_PURGE` | Shift+F2 | Main | Action · Clear history |
| `HOTKEY_READ` | F4 | Main | Reader · Read the selection |
| `HOTKEY_PANIC` | Esc | **Fixed** | Esc always cancels. 5b refuses Esc as a key for anything else, so a setting for it would only allow a clash. |

## AI

| Setting today | Default | Goes to | Note |
|---|---|---|---|
| `AI_PROVIDER` | builtin | Main | Built-in / Ollama / Custom. `openai` and `claude` become Custom, with Claude as a preset. |
| `AI_URL` | 127.0.0.1:8080 … | Main (Custom) | |
| `AI_MODEL` | (blank) | Main (Custom) | |
| `AI_API_KEY` | — | Main (Custom) | Kept in Credential Manager, never in the file. |
| `OLLAMA_MODEL_NAME` | (first installed) | Main (Ollama) | A picker filled from Ollama's list. |
| `OLLAMA_HOST_URL` | 127.0.0.1:11434 | Advanced | |
| `OLLAMA_KEEP_ALIVE` | 30m | Advanced | |
| `AI_LOAD_AT_START` | on | Advanced | |
| `POLISH_CLIPBOARD_CONTEXT` | auto | Advanced | auto / on / off. "auto" keeps the clipboard away from a Cloud provider. |
| `LLAMA_VARIANT` | auto | Advanced | |
| `AI_BUILTIN_REPO`, `AI_BUILTIN_FILE` | Gemma 4 E4B | Advanced | One "Built-in model" picker from a fixed list, not two text fields. |
| `AI_NUM_CTX`, `OLLAMA_NUM_CTX` | 8192 | **Fixed** | Measured: 8192 fits a five-minute dictation. Nobody needs to tune it. |
| `AI_BUILTIN_PORT` | 39281 | **Fixed** | Only matters if another program takes the port. The better fix is to try the next free port, not a setting. |
| `FALLBACK_LLM` | gemma2:27b | **Remove** | Ollama already falls back to its first installed model. This name is a leftover that would fail on most PCs. |

## Speech and recording

| Setting today | Default | Goes to | Note |
|---|---|---|---|
| `WHISPER_MODEL_NAME` | large-v3 | Main | |
| `WHISPER_DEVICE` | auto | Main | |
| `WHISPER_COMPUTE_TYPE` | float16 | Advanced | int8_float16 halves the graphics memory. |
| `MAX_RECORDING_SECONDS` | 300 | Advanced | |

## Reader

| Setting today | Default | Goes to | Note |
|---|---|---|---|
| `READER_VOICE` | af_heart | Main | |
| `READER_DEVICE` | auto | Advanced | |
| `READER_SMART_MODE` | off | Advanced | Phase 6 stops it from adding words to the vocabulary. |
| `READER_SMART_MAX_CHARS` | 1000 | **Fixed** | |
| `READER_LLM_TIMEOUT` | 10 s | **Fixed** | |
| `READER_FIRST_BATCH_CHARS` | 120 | **Fixed** | Measured tuning, not a choice. |
| `READER_BATCH_CHARS` | 300 | **Fixed** | Measured tuning, not a choice. |

## Notices, privacy, storage

| Setting today | Default | Goes to | Shown as |
|---|---|---|---|
| `ENABLE_AUDIO_CHIMES` | on | Main | Sounds |
| `ENABLE_TOAST_NOTIFICATIONS` | on | Main | Notifications |
| `LOG_DICTATION_TEXT` | off | Main (Privacy) | Show dictated words in the log |
| `MODELS_DIR` | %LOCALAPPDATA%\ZeroFlow\models | Advanced | Models folder. On your copy it is F:\HuggingFace. |

## New in 5b (not in the file yet)

| Setting | Default | Goes to |
|---|---|---|
| Dictation on / Reader on | on / on | Main and the tray menu |
| Microphone (stored by name) | Windows default | Main |
| Interface language | follows Windows | Main |
| Language pair | English + Arabic | Main (only one choice for now) |
| Keep dictation history | on | Main (Privacy) |
| Start with Windows | off | Main. Kept in the HKCU Run key, not in the file. |
| Reader speed | 1.0 | Main |

**Count:** 42 settings today (a script checked that every one is named in this table, and nothing else is). 21 go to Main, 12 to Advanced, 8 become Fixed and 1 is removed. 5b adds 7 new ones.
