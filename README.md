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
- **Bilingual, one key per language** — each record key **forces** its language (English on F5/F6, Arabic on F7/F8), so your speech is never misheard as the wrong language.
- **Explicit two-way translation** — `F9` translates **English → Arabic**, `F10` translates **Arabic → English**. The direction is fixed by the key, so it's always correct.
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

## 🛠️ Customizing
Almost everything is tweakable. See **[CONFIGURATION.md](CONFIGURATION.md)** for:
- changing hotkeys, the Whisper model, and GPU/CPU behaviour
- **using a different LLM provider** (LM Studio, llama.cpp, OpenAI, Anthropic…) and **adding an API key**
- editing the AI prompts, voice macros, punctuation, and vocabulary

And **[ARCHITECTURE.md](ARCHITECTURE.md)** for how the engine works internally, or
**[CHANGELOG.md](CHANGELOG.md)** for the full feature/fix list.

## 🔒 Privacy
Everything runs locally by default — audio never leaves the machine, transcription is
on-device (`faster-whisper`), and refinement uses your local Ollama. (If you switch to
a *cloud* LLM provider per CONFIGURATION.md, dictated text is sent to that provider.)
