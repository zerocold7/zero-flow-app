# Install Guide

> 🌍 **بالعربية:** [دليل التثبيت](INSTALL.ar.md) · 🟢 **Never installed anything like this?**
> The [Beginner Setup Guide](SETUP-CPU-LAPTOP.md) walks a laptop without a graphics card
> through every click.

One path for every PC. The only step that differs by hardware is **step 4** — and
`check_hardware.py` tells you which variant is yours.

---

## What you need
- **Windows 10 or 11, 64-bit.** (macOS and Linux are not supported.)
- **About 10 GB of free disk** for the programs and models (less on smaller tiers).
- **A microphone** — built-in is fine — and speakers for the reading voice.
- **Internet for the install only.** Once the models are downloaded, the engine runs
  offline.

---

## 1. Install Python, Git and Ollama
Open **PowerShell** (Start → type *PowerShell*) and run, one line at a time:

```powershell
winget install Python.Python.3.12
winget install Git.Git
winget install Ollama.Ollama
```

Close PowerShell and open it again, then check: `python --version` should print
`Python 3.12.x`. (Python 3.12 is the tested version.)

> **Microphone:** Settings → Privacy & security → Microphone → turn on *Microphone
> access* and *Let desktop apps access your microphone*. Without it the engine records
> silence.

## 2. Download the project
Keep it out of OneDrive-synced folders (Desktop, Documents) — put it on `C:\`:

```powershell
cd C:\
git clone https://github.com/zerocold7/local-voice-flow.git
cd local-voice-flow
```

## 3. Check your hardware

```powershell
python check_hardware.py
```

Note **your tier** and the **AI model** it names — steps 4 and 6 depend on them. What
each tier means: [HARDWARE.md](HARDWARE.md).

## 4. Install the Python packages
Create a private environment for the engine first — every launcher uses it
automatically:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
```

Then the variant for your tier:

**NVIDIA tiers** (`nvidia-desktop`, `nvidia-laptop`) — install the GPU build of torch
*first*, or pip quietly picks the CPU-only one and the voice runs on the CPU:

```powershell
.\venv\Scripts\python.exe -m pip install torch==2.5.1+cu121 --index-url https://download.pytorch.org/whl/cu121
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Also keep your NVIDIA driver up to date.

**`cpu-only` and `amd-intel-gpu`** — skip the 1.2 GB of NVIDIA libraries. This installs
everything in `requirements.txt` except the two `nvidia-` lines:

```powershell
.\venv\Scripts\python.exe -m pip install ((Get-Content requirements.txt) | Where-Object { $_ -match '^[A-Za-z]' -and $_ -notmatch '^nvidia-' })
```

This step takes several minutes.

## 5. Write your settings

```powershell
python check_hardware.py --apply
```

This creates `.env` with the settings for your tier (if you already have a `.env`, it
updates just those lines and saves the old one as `.env.bak`). Every other setting —
hotkeys, voice, chimes — is explained in [CONFIGURATION.md](../CONFIGURATION.md).

## 6. Download the AI model
Ollama runs in the background after install (icon by the clock). Pull the model the
checker named, for example:

```powershell
ollama pull qwen2.5:3b
```

Run `python check_hardware.py` again — every line under *Checks* should now say `[ok]`.

## 7. Start it
Double-click **`Launch_Zero.bat`** in the project folder. (If Windows shows *"Windows
protected your PC"*, click **More info → Run anyway**.)

The **first** start downloads the speech model and the voice — from 150 MB to 3 GB
depending on your tier. After that everything loads from disk.

- **Dictation is ready** when the window shows the `Z E R O -   F L O W   E N G I N E`
  box. Its *Speech to text* line tells you where the model loaded, e.g.
  `[Whisper small · CPU · int8]`.
- **Reading aloud is ready** when `🔵 [TTS] Voice model ready.` appears.

## 8. Try it
1. Click into Notepad. Press **`F5`** once, say a sentence, press **`F5`** again. Your
   words appear a moment later. (`F7` for Arabic.) *Tap the key — don't hold it.*
2. Highlight the text and press **`F4`** — the voice reads it. **`Esc`** stops it.

Laptop F-keys changing volume instead? Press **`Fn + Esc`** (Fn-Lock) or hold `Fn`.
The full key list, and the spoken commands, are in the [README](../README.md).

---

## Starting automatically with Windows
Press `Win + R`, type `shell:startup`, Enter. Right-click in that folder → *New →
Shortcut* → browse to `Launch_Zero_Silent.vbs`. The engine then starts hidden at every
sign-in; stop it from its tray icon (**Exit Engine**).

## Updating

```powershell
cd C:\local-voice-flow
git pull
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

(On `cpu-only` / `amd-intel-gpu`, use the step 4 variant instead of the last line.)
Your `.env`, vocabulary and history are never touched by an update. Re-run
`python check_hardware.py` to see whether the recommendations changed.

## Uninstalling
1. Exit the engine (tray icon → **Exit Engine**) and delete `C:\local-voice-flow`.
2. Downloaded models: delete the `models--Systran--faster-whisper-*` and
   `models--hexgrad--Kokoro-82M` folders in `%USERPROFILE%\.cache\huggingface\hub`.
3. The AI model: `ollama rm qwen2.5:3b` (or whichever you pulled). Python, Git and
   Ollama uninstall from *Settings → Apps*.

---

Something not working? [HARDWARE.md §5](HARDWARE.md#5-is-it-tuned-right-read-the-signs)
for speed problems, the [FAQ](FAQ.md) for everything else, and the two log files —
`flow_debug.log` and `reader_debug.log` in the project folder — for what actually happened.
