<p align="center">
  <img src="logo.jpg" alt="Zero- Flow Engine" width="340"/>
</p>

<h1 align="center">Zero- Flow Engine</h1>

<p align="center">
  <b>Speak and it types. Highlight and it reads.</b><br/>
  A private voice engine for Windows that runs entirely on your PC: English and Arabic
  dictation into any app, an AI that polishes and translates what you say, and a natural
  voice that reads any text back to you.
</p>

<p align="center">
  <img alt="Windows 10/11" src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4">
  <img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-3776AB">
  <img alt="Runs offline" src="https://img.shields.io/badge/runs-100%25%20offline-2F6F4F">
  <img alt="MIT license" src="https://img.shields.io/badge/license-MIT-lightgrey">
</p>

<p align="center">
  <a href="docs/INSTALL.md">Install</a> ·
  <a href="docs/HARDWARE.md">Hardware &amp; tuning</a> ·
  <a href="docs/FAQ.md">FAQ</a> ·
  <a href="docs/SETUP-CPU-LAPTOP.md">Beginner guide</a> ·
  <a href="docs/INSTALL.ar.md">بالعربية</a>
</p>

---

## What it does

Zero- Flow Engine sits in the system tray and answers to the function keys. It has two
halves that share one window and one tray icon.

**🎙️ Dictation (speech → text).** Click where you want to type, tap `F5`, speak, and tap
`F5` again. Your words are pasted at the cursor in Word, a browser, a chat app or a code
editor: anywhere `Ctrl+V` works.
- **English or Arabic**, each on its own key. The key sets the language, so one is
  never mistaken for the other.
- **Polish** (`F6` English, `F8` Arabic): the built-in AI removes "um"s, repeats and
  slips before pasting.
- **Translate** (`F9` English → Arabic, `F10` Arabic → English): speak one language,
  get the other.
- **Fix a line** (`Shift+F3`): with the cursor at the end of a line you typed, press it and
  the AI corrects that line in place.
- **Spoken commands:** start with *"new line"*, *"bullet"* or *"format code"*; end with
  *"and send"*, *"period"*, *"comma"* or *"question mark"*. Arabic has its own set
  ([Keys](#keys)).
- **Learns your words:** names and technical terms the AI picks up are saved to a
  vocabulary file, so they are spelled right next time.

**🔊 Reader (text → speech).** Highlight any text (a web page, a PDF, an email) and
press `F4`. A natural voice (Kokoro) starts reading after the first sentence, and `Esc`
stops it. Turn on *Smart LLM Cleaning* in the tray and the AI first strips menus, cookie
notices and other page clutter.

**🔒 Private by design.** Speech recognition (Whisper), the AI (Google's Gemma 4 via
llama.cpp) and the voice all run on your PC. Each model downloads once from Hugging
Face; after that the engine needs no internet, and nothing you say, type or read leaves
the machine. The one exception is your choice: pointing it at a cloud AI instead
([CONFIGURATION.md §6](CONFIGURATION.md#6-choosing-the-ai-provider)).

> **Status:** version 2.0 is in alpha, so expect changes between releases; see the
> [CHANGELOG](CHANGELOG.md).

## How it works

```mermaid
flowchart LR
    subgraph D["Dictation"]
        direction LR
        K["F5–F10"] --> M["Microphone"] --> W["Whisper<br/>speech → text"]
        W -->|raw| P["Pasted at<br/>your cursor"]
        W -->|polish / translate| L["Built-in AI<br/>(Gemma 4)"] --> P
    end
    subgraph R["Reader"]
        direction LR
        F4["F4"] --> S["Your highlighted<br/>text"] --> C["Clean-up"] --> V["Kokoro<br/>voice"] --> SP["Speakers"]
    end
```

The two halves run side by side and stay out of each other's way: starting a dictation
silences the reader instantly, and the reader never speaks while the microphone is
open. Internals: [ARCHITECTURE.md](ARCHITECTURE.md).

## Which PC do I need?

Any 64-bit Windows 10/11 PC with a microphone. A graphics card makes it faster; it is
not required. Run `python check_hardware.py` and it tells you which of these you are —
and writes the matching settings for you:

| Your PC | Speech model | Words appear after* | Guide |
|---|---|---|---|
| NVIDIA card, 8 GB+ | `large-v3` (best, best Arabic) | ≈1 s | [NVIDIA desktop](docs/HARDWARE.md#nvidia-desktop--8-gb-or-more) |
| NVIDIA laptop, 4–7 GB | `medium` / `small` | ≈1 s | [NVIDIA laptop](docs/HARDWARE.md#nvidia-laptop--4-to-7-gb) |
| No graphics card | `small` / `base` | ≈2–4 s | [CPU only](docs/HARDWARE.md#cpu-only--no-graphics-card) |
| AMD Radeon / Intel Arc | `small` | ≈2–4 s | [AMD / Intel](docs/HARDWARE.md#amd-radeon--intel-arc) |

\* For about 14 s of speech in the raw modes (`F5`/`F7`); Polish and Translate add the
AI's time. Only the NVIDIA desktop figure is measured (on an RTX 4070); the others are
estimates. Full numbers and tuning: **[HARDWARE.md](docs/HARDWARE.md)**.

## Quick start

```powershell
winget install Python.Python.3.12 ; winget install Git.Git
cd C:\ ; git clone https://github.com/zerocold7/zero-flow-app.git ; cd zero-flow-app
python check_hardware.py            # which tier am I?
```

Then install the packages for your tier, write your settings, install the built-in AI
(`tools\get_llama.py`) and start **`Launch_Zero.bat`** — every step, per tier, in
**[docs/INSTALL.md](docs/INSTALL.md)**. No Ollama needed: the AI runs inside the engine
(Ollama, LM Studio or a cloud AI such as Claude remain options —
[CONFIGURATION.md §6](CONFIGURATION.md#6-choosing-the-ai-provider)).
Never done anything like this? The **[Beginner Guide](docs/SETUP-CPU-LAPTOP.md)** walks
through every click (also as a [printable PDF](docs/Zero-Flow-Setup-Guide.pdf), and
[in Arabic](docs/SETUP-CPU-LAPTOP.ar.md) · [PDF](docs/Zero-Flow-Setup-Guide.ar.pdf)).

## Keys

**Record keys toggle:** tap once and talk, then tap **any** record key again to stop.
(Don't hold it — key repeat would start and stop the recording over and over.)

| Key | Dictation | | Key | Actions & reader |
|---|---|---|---|---|
| `F5` | English — as spoken | | `Shift+F1` | Tidy the learned vocabulary |
| `F6` | English — polished by the AI | | `Shift+F2` | Clear the debug log & history |
| `F7` | Arabic — as spoken | | `Shift+F3` | Fix the current line |
| `F8` | Arabic — polished by the AI | | `F4` | **Read the highlighted text aloud** |
| `F9` | Translate English → Arabic | | `Esc` | Cancel recording / stop reading |
| `F10` | Translate Arabic → English | | | |

Every key can be changed in `.env` ([CONFIGURATION.md §2](CONFIGURATION.md#2-changing-hotkeys)).
Laptop F-keys changing the volume instead? Press `Fn + Esc`.

**Spoken commands.** At the **start** of a dictation: *"new line"* (starts a new line),
*"bullet"* (`• ` prefix), *"format code"* (wraps it in backticks). At the **end**:
*"and send"* (presses Enter after pasting), *"period"*, *"comma"*, *"question mark"*.
Arabic: *"سطر جديد"*, *"قائمة"* (bullet), *"تنسيق كود"* (code), *"انتر"*, and at the end
*"نقطة"*, *"فاصلة"*, *"علامة استفهام"* for **.** **،** **؟**

**Tray menu** (by the clock): choose the voice, turn on Smart LLM Cleaning for the reader,
suspend the reader, **Unload AI model** (frees its memory; the next Polish loads it
again), or **Exit Engine**. Windows hides new tray icons — click `^` by the
clock to find it.

## Launchers

| Launcher | Runs |
|---|---|
| **`Launch_Zero.bat`** | **Both halves in one window, one tray icon — use this** |
| `Launch_Flow.bat` | Dictation only |
| `Launch_Reader.bat` | Reader only |

Each has a twin that starts with no window — `Launch_Zero_Silent.vbs`,
`Launch_Flow_Silent.vbs`, `Launch_Reader_Silent.vbs` — stopped from the tray icon. To start with Windows, see the [FAQ](docs/FAQ.md#can-it-start-with-windows).

## Documentation

| | English | العربية |
|---|---|---|
| **Install** — every PC, step by step | [INSTALL.md](docs/INSTALL.md) | [INSTALL.ar.md](docs/INSTALL.ar.md) |
| **Hardware & tuning** — tiers, measured speeds, fixes | [HARDWARE.md](docs/HARDWARE.md) | [HARDWARE.ar.md](docs/HARDWARE.ar.md) |
| **Beginner guide** — no graphics card, every click | [SETUP-CPU-LAPTOP.md](docs/SETUP-CPU-LAPTOP.md) · [PDF](docs/Zero-Flow-Setup-Guide.pdf) | [SETUP-CPU-LAPTOP.ar.md](docs/SETUP-CPU-LAPTOP.ar.md) · [PDF](docs/Zero-Flow-Setup-Guide.ar.pdf) |
| **FAQ** | [FAQ.md](docs/FAQ.md) | |
| **Every setting** — keys, models, prompts, other AI providers, languages | [CONFIGURATION.md](CONFIGURATION.md) | |
| **How it works inside** | [ARCHITECTURE.md](ARCHITECTURE.md) | |
| **What changed** | [CHANGELOG.md](CHANGELOG.md) | |

## When something goes wrong

1. `python check_hardware.py` — every line under *Checks* should say `[ok]`.
2. Look at `flow_debug.log` (dictation) and `reader_debug.log` (reader) in the project
   folder: every transcription, fallback and failure is recorded there, with how long
   each clip took.
3. [HARDWARE.md §5](docs/HARDWARE.md#5-is-it-tuned-right-read-the-signs) matches
   symptoms to fixes; the [FAQ](docs/FAQ.md) covers the rest.

## Privacy

Audio never leaves the machine: transcription runs on-device (`faster-whisper`), the AI
runs inside the engine (llama.cpp with Google's Gemma 4, listening on this PC only), and
the voice (`Kokoro`) is local too. The speech, voice and AI models download once from
Hugging Face — no account or `HF_TOKEN` needed — and after that the engine makes **no
network requests at all**. The only exception is one you choose: pointing it at a cloud
AI provider ([CONFIGURATION.md §6](CONFIGURATION.md#6-choosing-the-ai-provider)).

## For developers

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -t .
```

Run them in the engine's venv: the tests use the standard library's `unittest`, but
import the engine, so its packages must be installed. No models are loaded and nothing
plays; about half a minute. They cover what breaks quietly: voice macros and spoken
punctuation, quick start/stop/cancel of recordings, AI failures, the vocabulary and
history files, sentence batching, the reader's audio-thread safety and supervision,
one-copy-at-a-time, hardware tiers and presets. A few start real Python processes, to
test how Windows treats them. Developer tools: `requirements-dev.txt`. Start with
[ARCHITECTURE.md](ARCHITECTURE.md).

## License

[MIT](LICENSE) © 2026 zerocold7
