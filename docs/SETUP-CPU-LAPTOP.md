# Zero- Flow Engine — Beginner Setup Guide (Windows, no GPU needed)

> 📄 Prefer a printable / offline copy? **[Download the PDF version](Zero-Flow-Setup-Guide.pdf)**.

This guide takes you from a fresh Windows 11 laptop to a working Zero- Flow setup, **one step at a time** — written for someone who has never installed something like this before. It uses **CPU mode**, so **you do not need an NVIDIA graphics card**.

Just follow the steps in order. Every command is copy-paste.

---

## What you need before you start
- Your laptop, signed in to Windows 11.
- An internet connection — you'll download about **6–8 GB** total (one time only).
- About **30–45 minutes** (most of it is just waiting for downloads).
- Roughly **10 GB** of free disk space.
- Your **built-in microphone** (no extra hardware needed).

> 💡 **No NVIDIA GPU? That's completely fine.** This guide sets up **CPU mode**. It works exactly the same; transcription just takes about **1–4 seconds** after you release the key instead of being instant.

---

## Step 1 — Open PowerShell
PowerShell is the window where you'll type the setup commands.

1. Click the **Start** button (Windows logo, bottom-left).
2. Type the word **PowerShell**.
3. Click **Windows PowerShell** in the results. A dark window opens.

You'll type (or paste) one command at a time and press **Enter** after each. To paste a copied command, **right-click** inside the window.

---

## Step 2 — Install the three required programs
You need three free programs: **Python** (runs the engine), **Git** (downloads the project), and **Ollama** (the local AI). Paste these three lines into PowerShell, pressing **Enter** after each:

```powershell
winget install Python.Python.3.12
winget install Git.Git
winget install Ollama.Ollama
```

When they finish, **close PowerShell and open it again** (Step 1) so it notices the new programs. Then check they all installed:

```powershell
python --version
git --version
ollama --version
```

Each line should print a version number (for example `Python 3.12.x`).

> 💡 **"winget is not recognized"?** Open the **Microsoft Store**, search for **App Installer**, and click **Update**. Then close and reopen PowerShell and try again.

> 💡 **Typing `python` opens the Microsoft Store?** Go to **Settings → Apps → Advanced app settings → App execution aliases** and turn **OFF** the two entries named "python". (Or simply type `py` instead of `python` everywhere in this guide.)

---

## Step 3 — Turn on the microphone (do not skip!)
Windows hides the microphone from desktop apps by default. If you skip this, the engine will record **silence** and type nothing.

1. Open **Settings** (Start menu → the gear icon).
2. Go to **Privacy & security → Microphone**.
3. Turn **ON** "Microphone access".
4. Turn **ON** "Let desktop apps access your microphone".

---

## Step 4 — Download the project
Back in PowerShell, run these lines. They put the project in a folder called **local-voice-flow** inside your Documents:

```powershell
cd $HOME\Documents
git clone https://github.com/zerocold7/local-voice-flow.git
cd local-voice-flow
```

---

## Step 5 — Two small edits for a laptop without NVIDIA

**Edit A — remove the GPU-only lines.** Open the requirements file:

```powershell
notepad requirements.txt
```

Scroll to the bottom and **delete the last two lines** (`nvidia-cublas-cu12` and `nvidia-cudnn-cu12`). Save with **Ctrl+S**, then close Notepad. These are only for NVIDIA cards and would waste ~1.2 GB.

**Edit B — choose laptop-friendly AI models.** Create your settings file and open it:

```powershell
Copy-Item .env.example .env
notepad .env
```

Change these two lines so they read exactly like this, then save (Ctrl+S) and close:

```ini
WHISPER_MODEL_NAME="small"
FALLBACK_LLM="qwen2.5:3b"
```

> 💡 **Why:** the defaults (`large-v3` and `gemma2:27b`) are built for a big GPU and lots of memory. `small` + `qwen2.5:3b` fit comfortably in a 16 GB laptop.

---

## Step 6 — Install the engine's Python parts
These commands create a private folder named **venv** and download the needed libraries into it. Run them **in this order** (the last one takes a few minutes — wait until the prompt returns):

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## Step 7 — Download the local AI model
Ollama runs quietly in the background after install (look for its icon near the clock). Download a small bilingual model:

```powershell
ollama pull qwen2.5:3b
```

This is about 2 GB, one time only. Lighter option: `gemma2:2b`. Higher quality but slower: `qwen2.5:7b` (if you choose that, also put its name in `FALLBACK_LLM` in your `.env`).

---

## Step 8 — Start it for the first time
1. Open **File Explorer** and go to **Documents → local-voice-flow**.
2. Double-click **`Launch_Flow.bat`**.

> ⚠️ **If Windows shows a blue "Windows protected your PC" box**, click **More info**, then **Run anyway**. This is just Windows being cautious about a new file — it's your own project file.

A console window opens. The **first** launch downloads the Whisper "small" model (~500 MB) — let it finish. When you see a line like this, it's ready:

```
Whisper model active on CPU (int8)
```

Leave that window open (you can minimize it). **Closing the window stops the engine.**

---

## Step 9 — Test that it works
1. Open **Notepad** and click inside it so the cursor is blinking.
2. Hold **F5**, say "hello, this is a test", then release F5.
3. After a second or two, your words appear in Notepad.
4. Try **F7** and speak Arabic the same way.

If nothing appears, see **[Troubleshooting](#troubleshooting)** below.

---

## Step 10 — Hotkey reference
Hold the key, speak, release. The key **forces** the language, so it's never misheard.

| Key | What it does |
|-----|--------------|
| `F5` | Dictate **English — raw** (exactly as spoken) |
| `F6` | Dictate **English — polished** (AI cleans grammar/fillers) |
| `F7` | Dictate **Arabic — raw** |
| `F8` | Dictate **Arabic — polished** |
| `F9` | **Translate** English → Arabic |
| `F10` | **Translate** Arabic → English |
| `Shift + F1` | Tidy up the learned-vocabulary file |
| `Shift + F2` | Clear the debug log and dictation history |
| `Shift + F3` | Rewrite and fix the current line |
| `Esc` | Cancel the recording in progress |

---

## Step 11 — Everyday use: starting and stopping
- **Start:** double-click `Launch_Flow.bat` and minimize the window.
- **Stop:** close that console window (click the **X**).
- **Find the tray icon:** click the small **^** arrow next to the clock; the Zero- Flow icon lives there.
- **Ollama** starts automatically with Windows, so the AI features just work.

> 💡 **Run it invisibly:** double-click `Launch_Silent.vbs` to start with no window. To stop it then, open **Task Manager** (Ctrl+Shift+Esc), find **python**, and click **End task**. Stick with the visible `.bat` until you're comfortable.

---

## Troubleshooting

| If this happens… | Do this |
|---|---|
| **Nothing is typed when I speak** | Check microphone permissions (Step 3). Make sure you held the key the whole time you spoke. Look at the console window for a red error message. |
| **`python is not recognized`** | Close and reopen PowerShell. If it still fails, reinstall Python and tick "Add to PATH", or type `py` instead of `python`. |
| **`winget is not recognized`** | Update **App Installer** from the Microsoft Store, then reopen PowerShell. |
| **It types in the wrong language** | Use the matching key: F5/F6 for English, F7/F8 for Arabic. The key decides the language. |
| **Hotkeys do nothing in one specific app** | Right-click `Launch_Flow.bat` and choose **Run as administrator**. |
| **Polish / Translate does nothing** | Make sure Ollama is running: type `ollama list` and confirm your model is listed (Step 7). |
| **Everything feels too slow** | In `.env` set `WHISPER_MODEL_NAME="base"`, save, and restart the engine. |
| **SmartScreen blocks the launcher** | Click **More info**, then **Run anyway**. |

---

## Making it faster or more accurate
After changing any of these in `.env`, **save the file and restart the engine** (close the console and run the launcher again).

**Speech model** (`WHISPER_MODEL_NAME`):

| Value | Trade-off |
|---|---|
| `tiny` / `base` | Fastest, lowest accuracy. Good if "small" feels slow. |
| `small` | Recommended balance for a laptop (this guide's default). |
| `medium` | Better Arabic accuracy, noticeably slower on CPU. |

**AI model** (`FALLBACK_LLM`, pulled with `ollama pull`):

| Value | Trade-off |
|---|---|
| `gemma2:2b` | Lightest, fastest. |
| `qwen2.5:3b` | Recommended balance, good Arabic + English. |
| `qwen2.5:7b` | Best quality, slower on CPU. |

---

> 🔒 **Privacy:** everything in this guide runs **locally on your machine** — your voice and text are never uploaded. For deeper customization (other languages, other AI providers, prompts), see **[CONFIGURATION.md](../CONFIGURATION.md)**.
