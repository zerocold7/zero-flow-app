# Zero- Flow Engine — Beginner Setup Guide (Windows, no GPU needed)

> 📄 Prefer a printable / offline copy? **[Download the PDF version](Zero-Flow-Setup-Guide.pdf)**.
>
> 🌍 **بالعربية:** **[اقرأ هذا الدليل بالعربية](SETUP-CPU-LAPTOP.ar.md)** (نسخة Word: [.docx](SETUP-CPU-LAPTOP.ar.docx)).
>
> 🎮 **Have an NVIDIA, AMD or Intel graphics card?** Follow the [Install Guide](INSTALL.md) instead — it covers every kind of PC, and the [Hardware Guide](HARDWARE.md) explains what to expect from yours.

This guide takes you from a fresh Windows 11 laptop to a working Zero- Flow setup, **one step at a time** — written for someone who has never installed something like this before. It uses **CPU mode**, so **you do not need an NVIDIA graphics card**.

Zero- Flow does two things, entirely on your own machine:
- **Dictation** — press a key, speak English or Arabic, press it again, and your words are typed wherever your cursor is.
- **Reading aloud** — highlight any text, press `F4`, and a natural voice reads it to you.

Just follow the steps in order. Every command is copy-paste.

---

## What you need before you start
- Your laptop, signed in to Windows 11.
- An internet connection — you'll download about **6–8 GB** total (one time only).
- About **30–45 minutes** (most of it is just waiting for downloads).
- Roughly **10 GB** of free disk space.
- Your **built-in microphone** and speakers (no extra hardware needed).

> 💡 **No NVIDIA GPU? That's completely fine.** This guide sets up **CPU mode**. It works exactly the same; your words just take about **1–4 seconds** to appear after you stop recording, instead of being instant.

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

> ⚠️ **Avoid OneDrive.** New laptops often sync your **Desktop** and **Documents** folders to OneDrive, which can break file paths with confusing red errors during install. Put the project on the **`C:\` drive** directly instead.

Back in PowerShell, run these lines. They put the project in a folder at the root of your C: drive (`C:\local-voice-flow`):

```powershell
cd C:\
git clone https://github.com/zerocold7/local-voice-flow.git
cd local-voice-flow
```

---

## Step 5 — Two small edits for a laptop without NVIDIA

**Edit A — remove the GPU-only lines.** Open the requirements file:

```powershell
notepad requirements.txt
```

Find the **two lines that start with `nvidia-`** (`nvidia-cublas-cu12…` and `nvidia-cudnn-cu12…`) and delete just those two. Save with **Ctrl+S**, then close Notepad. They are only for NVIDIA cards and would waste ~1.2 GB.

> ⚠️ Delete **only** the two `nvidia-` lines. Keep the `kokoro` line near the bottom — that is the voice that reads text aloud.

**Edit B — choose laptop-friendly settings.** Create your settings file and open it:

```powershell
Copy-Item .env.example .env
notepad .env
```

Find these four lines and change them so they read exactly like this, then save (Ctrl+S) and close:

```ini
WHISPER_MODEL_NAME="small"
WHISPER_DEVICE="cpu"
OLLAMA_MODEL_NAME="qwen2.5:3b"
READER_DEVICE="cpu"
```

> 💡 **Why:** the default speech model (`large-v3`) is built for a big graphics card — on a laptop processor it takes longer than you took to speak. `small` for speech and `qwen2.5:3b` for the AI fit comfortably in a 16 GB laptop, and the two `cpu` lines tell the engine not to look for a graphics card.

> 💡 **Shortcut:** instead of editing by hand, run `python check_hardware.py --apply`. It looks at your laptop and writes the right lines for you — and says so if yours has only 8 GB of memory and needs even lighter settings.

---

## Step 6 — Install the engine's Python parts
These commands create a private folder named **venv** and download the needed libraries into it. Run them **in this order** (the last one takes several minutes — wait until the prompt returns):

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

This is about 2 GB, one time only. Lighter option: `gemma2:2b`. Higher quality but slower: `qwen2.5:7b`. Whichever you pull, put the **same name** in `OLLAMA_MODEL_NAME` in your `.env` (Step 5).

---

## Step 8 — Start it for the first time
1. Open **File Explorer** and go to **`C:\local-voice-flow`**.
2. Double-click **`Launch_Zero.bat`**.

> ⚠️ **If Windows shows a blue "Windows protected your PC" box**, click **More info**, then **Run anyway**. This is just Windows being cautious about a new file — it's your own project file.

A console window opens. The **first** launch downloads the speech model (~500 MB) and the reading voice (~350 MB) — let it finish. Later launches load everything from your own disk and don't need the internet at all.

**Dictation is ready** when the window shows a box titled **`Z E R O -   F L O W   E N G I N E`** with the list of keys under it. **Reading aloud is ready** a little later, when this line appears:

```
🔵 [TTS] Voice model ready.
```

Leave that window open (you can minimize it). **Closing the window stops the engine.**

---

## Step 9 — Test that it works

> ⌨️ **Laptop Fn-key trap (important!).** On most laptops, **F5–F10 are media keys** (volume/brightness) by default, so pressing `F5` alone won't reach the engine. Fix it once: press **`Fn + Esc`** to turn on **Fn-Lock** (this is the Lenovo/IdeaPad shortcut) — now the F-keys work with a single press. Or hold **`Fn`** together with the key every time (e.g. `Fn + F7`). If `Fn + Esc` doesn't work, look for a small padlock icon on the `Esc` key, or check your laptop's manual.

**Dictation:**
1. Open **Notepad** and click inside it so the cursor is blinking.
2. Press **F5** once (you'll hear a short beep), say "hello, this is a test", then press **F5** again.
3. After a second or two, your words appear in Notepad.
4. Try **F7** and speak Arabic the same way.

> 💡 **Tap, don't hold.** Each key starts recording on the first press and stops on the second. Holding it down makes it start and stop over and over.

**Reading aloud:**
1. Highlight a sentence in any window — the text you just dictated works.
2. Press **F4**. The voice reads it out. Press **Esc** to stop it early.

If nothing happens, see **[Troubleshooting](#troubleshooting)** below.

---

## Step 10 — Hotkey reference
Press the key, speak, press it again. The key **forces** the language, so it's never misheard.

| Key | What it does |
|-----|--------------|
| `F5` | Dictate **English — raw** (exactly as spoken) |
| `F6` | Dictate **English — polished** (AI cleans grammar/fillers) |
| `F7` | Dictate **Arabic — raw** |
| `F8` | Dictate **Arabic — polished** |
| `F9` | **Translate** English → Arabic |
| `F10` | **Translate** Arabic → English |
| `Shift + F1` | Tidy up the learned-vocabulary file (the old list is kept as a backup) |
| `Shift + F2` | Clear the debug log and dictation history |
| `Shift + F3` | Rewrite and fix the current line |
| `F4` | **Read the highlighted text aloud** (see Step 12) |
| `Esc` | Cancel the recording, or silence the reading |

**Spoken commands** work inside any dictation:
- Start with **"new line"** to begin a new line, **"bullet"** for a `•` bullet point, or **"format code"** to wrap the text as code.
- End with **"and send"** to press **Enter** after it is typed (handy in chat apps).
- End with **"period"**, **"comma"** or **"question mark"** to type the real mark.
- In Arabic: **"سطر جديد"** (new line), **"نقطة"** or **"قائمة"** (bullet), **"كود"** (code), **"انتر"** (Enter), and **"فاصلة"** / **"علامة استفهام"** at the end for **،** / **؟**.

---

## Step 11 — Everyday use: starting and stopping
- **Start:** double-click `Launch_Zero.bat` and minimize the window. (`Launch_Flow.bat` starts dictation only, without `F4`.)
- **Stop:** close that console window (click the **X**), or right-click the tray icon and choose **Exit Engine**.
- **Find the tray icon:** click the small **^** arrow next to the clock; the Zero- Flow icon lives there.
- **Ollama** starts automatically with Windows, so the AI features just work.

> 💡 **Run it invisibly:** double-click `Launch_Zero_Silent.vbs` to start with no window at all. To stop it, right-click the tray icon and choose **Exit Engine**. Stick with the visible `.bat` until you're comfortable — its window shows you what the engine is doing.

---

## Step 12 — Reading text aloud (`F4`)
Highlight any text — a web page, a PDF, a chat message — and press **`F4`**. A local voice reads it out. Press **`Esc`** to stop it; to read something else, press `Esc`, highlight the new text and press `F4`.

`F4` comes with `Launch_Zero.bat`, which this guide uses. (`Launch_Flow.bat` is dictation only.) The reader stays quiet while you are dictating, so it never talks over your microphone.

Right-click the tray icon to switch voice, to pause the reader (**Suspend Reader**), or to turn on **Smart LLM Cleaning**, which asks the local AI to strip page clutter (menus, cookie notices) before reading.

> 🐢 **On a laptop with no NVIDIA card, expect a short pause before the voice starts.** The voice model loads in the background when the engine starts; wait for `Voice model ready.` before your first `F4`. After that the voice starts once the first sentence is ready and keeps going smoothly while the rest is prepared. Reading a paragraph at a time rather than a whole page keeps that first pause short.

---

## Troubleshooting

| If this happens… | Do this |
|---|---|
| **Nothing is typed when I speak** | Check microphone permissions (Step 3). Press the key **once** to start and **once more** to stop — don't hold it. Look at the console window for a red error message. |
| **The console says "Could not open the microphone"** | The microphone is off, unplugged, or blocked — go through Step 3 again, then restart the engine. |
| **`python is not recognized`** | Close and reopen PowerShell. If it still fails, reinstall Python and tick "Add to PATH", or type `py` instead of `python`. |
| **`winget is not recognized`** | Update **App Installer** from the Microsoft Store, then reopen PowerShell. |
| **It types in the wrong language** | Use the matching key: F5/F6 for English, F7/F8 for Arabic. The key decides the language. |
| **Hotkeys do nothing in one specific app** | Right-click `Launch_Zero.bat` and choose **Run as administrator**. |
| **Polish / Translate types my words unchanged** | Make sure Ollama is running: type `ollama list` and check that the name in `OLLAMA_MODEL_NAME` in your `.env` is listed exactly (Step 7). A mismatch shows up in `flow_debug.log` as `Ollama returned HTTP 404`. |
| **`F4` does nothing** | Make sure the text is **highlighted** first, and that the window has shown `Voice model ready.` The reader won't speak while a dictation is recording. Check you started `Launch_Zero.bat`, not `Launch_Flow.bat`. |
| **Everything feels too slow** | In `.env` set `WHISPER_MODEL_NAME="base"`, save, and restart the engine. |
| **SmartScreen blocks the launcher** | Click **More info**, then **Run anyway**. |
| **Pressing F5–F10 does nothing at all** | Your laptop's F-keys are in media mode. Press `Fn + Esc` to enable Fn-Lock (Step 9), or hold `Fn` together with the key. |
| **The laptop gets hot / fans get loud** | Use the raw modes `F5`/`F7` (they skip the AI). Confirm `.env` has `small` + `qwen2.5:3b` (not `medium`/`7b`). Drop to `base` for more cooling. See below. |
| **Something else went wrong** | Open `flow_debug.log` (dictation) or `reader_debug.log` (reading) in `C:\local-voice-flow` with Notepad — the last lines say what happened. |

---

## Keeping your laptop cool & fast
On a CPU laptop, **bigger models = more heat.** The biggest heat source is the AI model (Ollama), which works your CPU hard for a few seconds whenever you **polish** or **translate**. To stay cool:

- **For the least heat, use the raw modes `F5` (English) and `F7` (Arabic).** They type exactly what you say **without** running the AI, so the CPU barely warms up. Only use `F6`/`F8` (polish) and `F9`/`F10` (translate) when you actually need them — those are what run the AI model.
- **The heat is momentary.** The engine only works the CPU while it's processing (the few seconds after you stop a recording, or while it prepares speech). The rest of the time it sits idle and cool.
- **Still warm or slow?** Set `WHISPER_MODEL_NAME="base"` in `.env` (faster and cooler), then restart.
- **Keep `.env` light:** `small` + `qwen2.5:3b`. Avoid `medium` and `qwen2.5:7b` on a laptop — they're the usual cause of fan noise and heat.
- **Airflow:** use the laptop on a hard surface (not a bed or cushion) so the vents aren't blocked.

---

## Making it faster or more accurate
After changing any of these in `.env`, **save the file and restart the engine** (close the console and run the launcher again).

**Speech model** (`WHISPER_MODEL_NAME`):

| Value | Trade-off |
|---|---|
| `tiny` / `base` | Fastest, lowest accuracy. Good if "small" feels slow. |
| `small` | Recommended balance for a laptop (this guide's default). |
| `medium` | Better Arabic accuracy, noticeably slower on CPU. |

**AI model** (`OLLAMA_MODEL_NAME` — download it first with `ollama pull <name>`):

| Value | Trade-off |
|---|---|
| `gemma2:2b` | Lightest, fastest. |
| `qwen2.5:3b` | Recommended balance, good Arabic + English. |
| `qwen2.5:7b` | Best quality, slower on CPU. |

---

> 🔒 **Privacy:** everything in this guide runs **locally on your machine** — your voice and text are never uploaded. For deeper customization (other languages, other AI providers, prompts), see **[CONFIGURATION.md](../CONFIGURATION.md)**.
