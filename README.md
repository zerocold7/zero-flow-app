<p align="center">
  <img src="logo.jpg" alt="Zero- Flow Engine" width="340"/>
</p>

<h1 align="center">Zero- Flow Engine</h1>

<p align="center">
  A high-performance, fully local, bilingual (Arabic / English) voice engine for
  Windows 11 — speech into any app in one half, the screen read back aloud in the other.
</p>

---

## ✨ Features
- **GPU-accelerated, automatic CPU fallback** — runs `faster-whisper large-v3` on an NVIDIA GPU (CUDA, `float16`). If the CUDA libraries are unavailable it falls back to optimized CPU `int8` automatically, and this is verified with a real inference at startup (no silent mid-dictation failures).
- **Bilingual, one key per language** — each record key **forces** its language (English on F5/F6, Arabic on F7/F8), so your speech is never misheard as the wrong language.
- **Explicit two-way translation** — `F9` translates **English → Arabic**, `F10` translates **Arabic → English**. The direction is fixed by the key, so it's always correct.
- **Dynamic local LLM** — auto-discovers and binds to whatever model your local **Ollama** instance is serving (no hardcoded model). Powers Polish, Translate, and line-correction.
- **Self-evolving vocabulary** — learns proper nouns and technical terms on the fly via `[LEARN: …]` and remembers them across sessions.
- **Voice macros** — spoken tokens like *“new line”*, *“bullet”*, *“format code”*, *“and send”* become real keystrokes and formatting.
- **Reads text back to you** — highlight anything, press `F4`, and a local **Kokoro** voice speaks it. An optional LLM pass strips web-page junk first, and `Esc` silences it instantly.
- **Background-friendly** — system-tray icon, optional toast notifications and audio chimes. Nothing ever leaves your machine.

## 🧱 Two halves, one engine
| Half | Direction | Entry point |
|------|-----------|-------------|
| **Flow** | speech → text | `local_flow.py` |
| **Reader** | text → speech | `reader/` (`python -m reader`) |

**Three ways to run them:**

| Launcher | What you get |
|----------|--------------|
| **`Launch_Zero.bat`** | **The whole engine: one window, one tray icon** — recommended |
| `Launch_Flow.bat` / `Launch_Reader.bat` | One half only |
| `Launch_All.bat` | Both halves in two separate windows, if you prefer them apart |

Each has a `_Silent.vbs` twin that starts it hidden.

**You do not need both.** Each half is a complete program — run whichever you want.

**`Launch_Zero.bat` is the one to use.** It runs dictation itself and starts the
reader as a child process that shares the same console window, so you get one window
and one tray icon while both models still get the GPU (~0.2 s to the first spoken
word). Because they are separate processes, a crash in one half cannot take the other
down. `Launch_All.bat` does the same thing in two visible windows if you prefer that.

They share `flow_core.py` (config, the Ollama client, the learned vocabulary),
`personas.py` (prompts and word lists) and `engine_ui.py` (console, chimes, toasts,
tray) — so there is one `.env` and one vocabulary for both.

**Running both is safe**, merged or separate. Their hotkeys don't overlap, and the
two coordinate over the one resource they'd otherwise fight for — the microphone:
- Starting a dictation **silences the reader immediately**.
- The reader **refuses to speak while the mic is open**, so Whisper can never
  transcribe the synthetic voice back at you.
- `Esc` does the right thing in whichever half is busy.
- Merged, they also share one clipboard lock and one debug log; run separately, each
  half keeps its own log so neither corrupts the other's.

## 🧩 Requirements
- Windows 11
- Python 3.12
- A running [Ollama](https://ollama.com) instance with at least one model pulled
- *(Recommended)* an NVIDIA GPU with a current driver for real-time speed

## 🚀 Setup

> 📄 **Note:** the two setup **PDFs** below predate the read-aloud half and still
> describe a dictation-only engine. The Markdown guides beside them are current.

> 🟢 **New here? Never installed something like this before?**
> Follow the **[Beginner Setup Guide — step by step, no GPU needed](docs/SETUP-CPU-LAPTOP.md)**
> (also available as a **[printable PDF](docs/Zero-Flow-Setup-Guide.pdf)**, or the
> **[laptop edition PDF](docs/Zero-Flow-Laptop-Setup-Guide.pdf)**). It covers everything
> below in plain language, including microphone permissions and troubleshooting.
> <br>🌍 **بالعربية:** **[دليل التثبيت للمبتدئين (نسخة اللابتوب)](docs/SETUP-CPU-LAPTOP.ar.md)** — أو [نسخة Word](docs/SETUP-CPU-LAPTOP.ar.docx).

**Quick version (if you've done this before):**
1. Clone this repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   This includes the CUDA runtime libraries (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) needed for GPU acceleration. Running **CPU-only**? Remove those two lines from `requirements.txt` to save ~1.2 GB.
3. Copy `.env.example` to `.env` and adjust to taste.
4. Make sure Ollama is running.
5. Launch:
   - **`Launch_Flow.bat`** — dictation, visible console (recommended for the first run)
   - **`Launch_Silent.vbs`** — dictation, invisible background process
   - **`Launch_Reader.bat`** / **`Launch_Reader_Silent.vbs`** — the read-aloud half
     (start it as well as, or instead of, dictation)
   - **`Launch_All.bat`** / **`Launch_All_Silent.vbs`** — both halves, two processes
   - **`Launch_Zero.bat`** / **`Launch_Zero_Silent.vbs`** — both halves, one process
     and one window (recommended)

> **Windows 11 tray tip:** new tray icons are hidden by default. Click the `^` arrow next to the clock to find the Zero- Flow icon, or pin it permanently via *Settings → Personalization → Taskbar → Other system tray icons*.

## ⌨️ Hotkeys (configurable in `.env`)
| Key | Action |
|-----|--------|
| `F5` | Dictate **English — raw** (as spoken) |
| `F6` | Dictate **English — polish** (AI cleanup) |
| `F7` | Dictate **Arabic — raw** |
| `F8` | Dictate **Arabic — polish** (AI cleanup) |
| `F9` | **Translate** English → Arabic |
| `F10` | **Translate** Arabic → English |
| `Shift + F1` | Run AI vocabulary maintenance |
| `Shift + F2` | Clear the debug log & dictation history |
| `Shift + F3` | Rewrite & correct the current line |
| `Esc` | Cancel the current recording (does nothing when idle) |

**Reader** (`Launch_Reader.bat`, separate process):

| Key | Action |
|-----|--------|
| `F4` | Read the **highlighted text** aloud |
| `Esc` | Silence the reader immediately |

Voice selection, the optional LLM clean-up, and suspending the listener live in the
reader's tray menu. The first `F4` of a session loads the voice model, so it takes a
few seconds; every press after that is instant.

## 🛠️ Customizing
Almost everything is tweakable. See **[CONFIGURATION.md](CONFIGURATION.md)** for:
- changing hotkeys, the Whisper model, and GPU/CPU behaviour
- **using a different LLM provider** (LM Studio, llama.cpp, OpenAI, Anthropic…) and **adding an API key**
- editing the AI prompts, voice macros, punctuation, and vocabulary

And **[ARCHITECTURE.md](ARCHITECTURE.md)** for how the engine works internally, or
**[CHANGELOG.md](CHANGELOG.md)** for the full feature/fix list.

## 🧪 Tests
The text-handling logic — voice macros, spoken punctuation, sentence batching,
vocabulary learning — is covered by a small suite using only the standard library:

```bash
python -m unittest discover -s tests
```

No extra dependencies, no model loading; it runs in well under a second.

## 🔒 Privacy
Everything runs locally by default — audio never leaves the machine, transcription is
on-device (`faster-whisper`), and refinement uses your local Ollama. (If you switch to
a *cloud* LLM provider per CONFIGURATION.md, dictated text is sent to that provider.) 
