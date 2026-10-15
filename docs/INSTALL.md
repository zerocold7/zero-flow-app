# Install Guide

> 🌍 **بالعربية:** [دليل التثبيت](INSTALL.ar.md) · 🟢 **Never installed anything like this?**
> The [Beginner Setup Guide](SETUP-CPU-LAPTOP.md) walks a laptop without a graphics card
> through every click.

One path for every PC. The only step that differs by hardware is **step 4** — and
`check_hardware.py` tells you which variant is yours.

---

## What you need
- **Windows 10 or 11, 64-bit.** (macOS and Linux are not supported.)
- **About 15 GB of free disk** for the programs and models (less on smaller tiers) —
  the AI model alone is 5.15 GB.
- **A microphone** — built-in is fine — and speakers for the reading voice.
- **Internet for the install only.** Once the models are downloaded, the engine runs
  offline.

---

## 1. Install Python and Git
Open **PowerShell** (Start → type *PowerShell*) and run, one line at a time:

```powershell
winget install Python.Python.3.12
winget install Git.Git
```

That is all you install by hand: the AI model runs **built into the engine** (step 6), so
Ollama is not needed.

Close PowerShell and open it again, then check: `python --version` should print
`Python 3.12.x`. (Python 3.12 is the tested version.)

> **Microphone:** Settings → Privacy & security → Microphone → turn on *Microphone
> access* and *Let desktop apps access your microphone*. Without it the engine records
> silence.

## 2. Download the project
Keep it out of OneDrive-synced folders (Desktop, Documents) — put it on `C:\`:

```powershell
cd C:\
git clone https://github.com/zerocold7/zero-flow-app.git
cd zero-flow-app
```

## 3. Check your hardware

```powershell
python check_hardware.py
```

Note **your tier** — step 4 depends on it. What each tier means:
[HARDWARE.md](HARDWARE.md).

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
.\venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints.txt
```

Also keep your NVIDIA driver up to date.

**`cpu-only` and `amd-intel-gpu`** — skip the 1.2 GB of NVIDIA libraries. This installs
everything in `requirements.txt` except the two `nvidia-` lines:

```powershell
.\venv\Scripts\python.exe -m pip install ((Get-Content requirements.txt) | Where-Object { $_ -match '^[A-Za-z]' -and $_ -notmatch '^nvidia-' }) -c constraints.txt
```

This step takes several minutes.

## 5. Write your settings

```powershell
python check_hardware.py --apply
```

This creates `.env` with the settings for your tier (if you already have a `.env`, it
updates just those lines and saves the old one as `.env.bak`). Every other setting —
hotkeys, voice, chimes — is explained in [CONFIGURATION.md](../CONFIGURATION.md).

## 6. Install the built-in AI
Polish, Translate and the other AI keys run an AI model on llama.cpp's `llama-server`,
which the engine starts and stops by itself. Install it once:

```powershell
.\venv\Scripts\python.exe tools\get_llama.py
```

It picks the build your PC needs, downloads the pinned llama.cpp release (build
`b11619`) from GitHub ([github.com/ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp)),
checks every archive against its published SHA-256, and unpacks it into
`runtime\llama\<build>\`:

| Build | For | Download |
|---|---|---|
| `cuda` | NVIDIA cards | 625 MB |
| `vulkan` | AMD Radeon / Intel Arc cards (not tested yet) | 31 MB |
| `cpu` | everything else | 19 MB |

To choose the build yourself: `--variant cuda`, `--variant vulkan` or `--variant cpu`.

The **AI model** itself downloads automatically the first time the engine starts — no
account, nothing to pull: Google's **Gemma 4 E4B** (5.15 GB, Apache 2.0 licence). On a
4–5 GB NVIDIA laptop card, or with 8 GB of RAM or less, step 5 picked the smaller
**Gemma 4 E2B** (3.35 GB) instead; its Arabic has not been tested yet.

Run `python check_hardware.py` again — every line under *Checks* should now say `[ok]`.

> **Rather use Ollama, or a cloud AI?** Set `AI_PROVIDER` in `.env` —
> [CONFIGURATION.md §6](../CONFIGURATION.md#6-choosing-the-ai-provider). If the built-in
> AI is not installed, the engine says so when it starts (in the window, the log and a
> pop-up, naming `tools/get_llama.py`) and uses Ollama instead.

## 7. Start it
Double-click **`Launch_Zero.bat`** in the project folder. (If Windows shows *"Windows
protected your PC"*, click **More info → Run anyway**.)

The **first** start downloads the speech model and the voice — from 150 MB to 3 GB
depending on your tier — and the AI model (5.15 GB, or 3.35 GB for Gemma 4 E2B). After
that everything loads from disk.

- **Dictation is ready** when the window shows the `Z E R O -   F L O W   E N G I N E`
  box. Its *Speech to text* line tells you where the model loaded, e.g.
  `[Whisper small · CPU · int8]`.
- **Reading aloud is ready** when `🔵 [TTS] Voice model ready.` appears.
- The box's *AI model* line names the AI, e.g. `Gemma 4 E4B · built in (cuda)`.

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
cd C:\zero-flow-app
git pull
.\venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints.txt
```

(On `cpu-only` / `amd-intel-gpu`, use the step 4 variant instead of the last line.)
Updating from a version that used Ollama? Also run step 6
(`.\venv\Scripts\python.exe tools\get_llama.py`) — until you do, the engine keeps using
Ollama and says so at start-up.
Your `.env`, vocabulary and history are never touched by an update. Re-run
`python check_hardware.py` to see whether the recommendations changed.

## Uninstalling
1. Exit the engine (tray icon → **Exit Engine**) and delete `C:\zero-flow-app` —
   the built-in AI's `runtime\` folder goes with it.
2. Downloaded models: delete the `models--Systran--faster-whisper-*`,
   `models--hexgrad--Kokoro-82M` and `models--google--gemma-4-E4B-it-qat-q4_0-gguf` (or
   `…-E2B-…`) folders in `%USERPROFILE%\.cache\huggingface\hub`.
3. Python and Git uninstall from *Settings → Apps*. If you used Ollama too, remove its
   model first (`ollama rm <name>`), then Ollama itself the same way.

---

Something not working? [HARDWARE.md §5](HARDWARE.md#5-is-it-tuned-right-read-the-signs)
for speed problems, the [FAQ](FAQ.md) for everything else, and the two log files —
`flow_debug.log` and `reader_debug.log` in the project folder — for what actually happened.
