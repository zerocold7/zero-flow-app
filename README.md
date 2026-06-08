<p align="center">
  <img src="logo.jpg" alt="Zero- Flow Engine" width="340"/>
</p>

<h1 align="center">Zero- Flow Engine</h1>

<p align="center">
  A high-performance, fully local, bilingual (Arabic / English) voice-dictation
  and text-injection engine for Windows 11.
</p>

---

## ✨ Features
- **GPU-accelerated, automatic CPU fallback** — runs `faster-whisper large-v3` on an NVIDIA GPU (CUDA, `float16`). If the CUDA libraries are unavailable it falls back to optimized CPU `int8` automatically, and this is verified with a real inference at startup (no silent mid-dictation failures).
- **Truly bilingual** — speak Arabic or English in any mode and the transcription stays in the language you actually spoke.
- **Smart two-way translation (`F11`)** — the engine detects the language you spoke and translates to the *other* one: speak **Arabic → get English**, speak **English → get Arabic**. One key, both directions, no toggles.
- **Dynamic local LLM** — auto-discovers and binds to whatever model your local **Ollama** instance is serving (no hardcoded model). Powers Polish, Translate, and line-correction.
- **Self-evolving vocabulary** — learns proper nouns and technical terms on the fly via `[LEARN: …]` and remembers them across sessions.
- **Voice macros** — spoken tokens like *“new line”*, *“bullet”*, *“format code”*, *“and send”* become real keystrokes and formatting.
- **Background-friendly** — system-tray icon, optional toast notifications and audio chimes. Nothing ever leaves your machine.

## 🧩 Requirements
- Windows 11
- Python 3.12
- A running [Ollama](https://ollama.com) instance with at least one model pulled
- *(Recommended)* an NVIDIA GPU with a current driver for real-time speed

## 🚀 Setup
1. Clone this repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   This includes the CUDA runtime libraries (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) needed for GPU acceleration. Running **CPU-only**? Remove those two lines from `requirements.txt` to save ~1.2 GB.
3. Copy `.env.example` to `.env` and adjust to taste.
4. Make sure Ollama is running.
5. Launch:
   - **`Launch_Flow.bat`** — visible console (recommended for the first run)
   - **`Launch_Silent.vbs`** — runs invisibly in the background

> **Windows 11 tray tip:** new tray icons are hidden by default. Click the `^` arrow next to the clock to find the Zero- Flow icon, or pin it permanently via *Settings → Personalization → Taskbar → Other system tray icons*.

## ⌨️ Hotkeys (configurable in `.env`)
| Key | Action |
|-----|--------|
| `F9` | Record — **Raw** dictation (inject exactly as spoken) |
| `F10` | Record — **AI Polish** (grammar / cleanup via Ollama) |
| `F11` | Record — **Auto-Translate** (Arabic ⇄ English, direction auto-detected) |
| `F8` | Record — **Force English** (skip auto-detect, always transcribe as English) |
| `Ctrl + F10` | Rewrite & correct the current line |
| `Ctrl + F11` | Run AI maintenance on the learned vocabulary |
| `Ctrl + F12` | Clear the debug log & dictation history |
| `Esc` | Cancel the current recording (does nothing when idle) |

## 🔒 Privacy
Everything runs locally — audio never leaves the machine, transcription is on-device
(`faster-whisper`), and all refinement uses your local Ollama. No cloud APIs.
