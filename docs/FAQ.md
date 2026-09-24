# FAQ

**The basics**
- [What is Zero- Flow?](#what-is-zero--flow)
- [Do I need a graphics card?](#do-i-need-a-graphics-card)
- [Does it need the internet? Does anything leave my PC?](#does-it-need-the-internet-does-anything-leave-my-pc)
- [Which Windows? Mac? Linux?](#which-windows-mac-linux)
- [Which languages?](#which-languages)
- [Do I need a Hugging Face account or an `HF_TOKEN`?](#do-i-need-a-hugging-face-account-or-an-hf_token)

**Using it**
- [Which apps can it type into?](#which-apps-can-it-type-into)
- [Why do I tap the key instead of holding it?](#why-do-i-tap-the-key-instead-of-holding-it)
- [My laptop's F-keys change the volume instead](#my-laptops-f-keys-change-the-volume-instead)
- [It typed "Thanks for watching!" — I never said that](#it-typed-thanks-for-watching--i-never-said-that)
- [What happened to the picture I had copied?](#what-happened-to-the-picture-i-had-copied)
- [Can it start with Windows?](#can-it-start-with-windows)

**Tuning and problems**
- [It's too slow / my laptop gets hot](#its-too-slow--my-laptop-gets-hot)
- [Polish or Translate gives me my words back unchanged](#polish-or-translate-gives-me-my-words-back-unchanged)
- [Where are my settings, logs and learned words?](#where-are-my-settings-logs-and-learned-words)
- [How do I update or uninstall it?](#how-do-i-update-or-uninstall-it)

---

### What is Zero- Flow?
A voice engine for Windows that runs entirely on your own PC, in two halves:
**dictation** (press a key, speak English or Arabic, press again — the text is typed
where your cursor is, optionally polished or translated by a local AI) and **reading
aloud** (highlight any text, press `F4`, and a natural voice reads it). See the
[README](../README.md).

### Do I need a graphics card?
No. Everything runs on the CPU too — you just wait a little longer (2–4 s instead of
about 1 s for a sentence). An NVIDIA card makes it near-instant. [HARDWARE.md](HARDWARE.md)
covers every kind of PC.

### Does it need the internet? Does anything leave my PC?
Only to install and to download the models once. After that it runs fully offline:
your voice, your text and your clipboard never leave the machine. The speech model and
voice load from your disk with no network request at all. The one exception is if
*you* point it at a cloud AI provider (see [CONFIGURATION.md §6](../CONFIGURATION.md#6-using-a-different-llm-provider-instead-of-ollama)).

### Which Windows? Mac? Linux?
Windows 10 or 11, 64-bit. macOS and Linux are not supported: the engine hooks the
Windows keyboard, clipboard and speaker APIs directly. Windows on ARM (Snapdragon) is
untested.

### Which languages?
Dictation: **English and Arabic**, each forced by its own key so it is never misheard,
plus translation between them. Other languages can replace either one — Whisper knows
about 99 — see [CONFIGURATION.md §4](../CONFIGURATION.md#4-changing-the-languages-eg-arabic--french).
The reading voice is English.

### Do I need a Hugging Face account or an `HF_TOKEN`?
No. The models are public and download once without an account. Earlier versions asked
Hugging Face about the models on every start, which made it print *"You are sending
unauthenticated requests to the HF Hub"*; the engine no longer contacts it at all once
the models are on disk.

### Which apps can it type into?
Any app where `Ctrl+V` pastes text — Word, browsers, chat apps, code editors, Notepad.
It pastes through the clipboard and puts your clipboard back afterwards. If one
particular app ignores the hotkeys, run the launcher as administrator (that app is
probably running as administrator itself).

### Why do I tap the key instead of holding it?
Each record key is a switch: the first press starts recording, the next press of any
record key stops it. Holding it down makes Windows repeat the key, which starts and
stops the recording over and over. `Esc` cancels a recording.

### My laptop's F-keys change the volume instead
Most laptops use F1–F12 for brightness and volume by default. Press `Fn + Esc` to turn
on Fn-Lock (on many Lenovo, HP and ASUS models), or hold `Fn` with the key. You can also
move the hotkeys to other keys in `.env` — [CONFIGURATION.md §2](../CONFIGURATION.md#2-changing-hotkeys).

### It typed "Thanks for watching!" — I never said that
Whisper sometimes invents a stock phrase when a clip is nearly silent. The engine
already drops clips under 0.4 s; beyond that, speak a little closer to the microphone
and stop the recording right after you finish speaking.

### What happened to the picture I had copied?
Dictation, `F4` and `Shift+F3` all borrow the clipboard and restore it afterwards — but
only *text* can be restored. If an image was on the clipboard, it is gone after a
dictation. Copy it again.

### Can it start with Windows?
Yes: `Win + R` → `shell:startup` → create a shortcut there to `Launch_Zero_Silent.vbs`.
It then starts hidden at every sign-in; stop it from the tray icon (**Exit Engine**).

### It's too slow / my laptop gets hot
Run `python check_hardware.py` to make sure the settings match your PC, then see
[HARDWARE.md §5](HARDWARE.md#5-is-it-tuned-right-read-the-signs) (what to change for
each symptom) and [§6](HARDWARE.md#6-laptops-heat-battery-and-noise) (heat). The quickest
win: use the raw modes `F5`/`F7`, which never run the AI model.

### Polish or Translate gives me my words back unchanged
Either the AI model did not answer, or it answered in the wrong language and the
engine pasted your own words rather than, say, Chinese. `flow_debug.log` says which:
- `Ollama request failed` — Ollama is not running (start it; its icon sits by the clock).
- `Ollama returned HTTP 404` — no model by the name in `OLLAMA_MODEL_NAME`; check
  `ollama list`, or `ollama pull` it.
- `The AI did not answer in 'ar'` — the model drifted out of Arabic. Some small models
  do this often; [HARDWARE.md](HARDWARE.md#ai-model--ollama_model_name) lists which
  ones stay in Arabic.

### Where are my settings, logs and learned words?
All in the project folder, and none of it is uploaded anywhere:

| File | What |
|---|---|
| `.env` | your settings |
| `flow_debug.log`, `reader_debug.log` | what each half did — look here first when something goes wrong |
| `flow_history.md` | everything you dictated (trimmed automatically; `Shift+F2` clears it) |
| `flow_vocabulary.txt` | names and terms the engine has learned (`Shift+F1` tidies it) |

### How do I update or uninstall it?
See [INSTALL.md — Updating](INSTALL.md#updating) and [Uninstalling](INSTALL.md#uninstalling).
Updates never touch your `.env`, history or vocabulary.
