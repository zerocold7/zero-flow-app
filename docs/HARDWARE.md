# Hardware & Tuning Guide

> 🌍 **بالعربية:** [دليل العتاد والضبط](HARDWARE.ar.md)

Zero- Flow runs up to three AI models on your own PC. How fast it feels depends on
**where each one runs**:

| Model | Does | Runs on |
|---|---|---|
| **Whisper** (faster-whisper) | your speech → text | NVIDIA GPU, or the CPU |
| **Ollama** (a local LLM) | Polish, Translate, fix-line — *only* those keys | whatever Ollama supports: NVIDIA, many AMD cards, or the CPU |
| **Kokoro** | text → the reading voice (`F4`) | NVIDIA GPU, or the CPU |

Everything works on every tier — the difference is how long you wait. This guide
tells you which settings suit your machine, what to expect, and how to tell if it is
tuned right.

---

## 1. Find your tier — let the checker do it

```powershell
python check_hardware.py
```

It needs nothing installed beyond Python, so you can run it straight after
downloading the project. It reads your graphics card, its memory, your RAM and CPU,
and prints your tier, the settings to use, and anything still missing:

```
GPU    : NVIDIA GeForce RTX 4070 — 12.0 GB (graphics card)
GPU    : Intel(R) UHD Graphics 750 — 2.0 GB (built-in graphics, not used)

Your tier: nvidia-desktop — NVIDIA graphics card, 8 GB or more

Recommended settings (presets/nvidia-desktop.env):
  WHISPER_MODEL_NAME="large-v3"
  ...
Checks:
  [ok] torch 2.5.1+cu121 (CUDA build)
  [!!] Ollama does not have qwen2.5:7b yet: ollama pull qwen2.5:7b
```

Then write those settings into your `.env` (everything else you have set is kept, and
the old file is saved as `.env.bak`):

```powershell
python check_hardware.py --apply
```

Disagree with its choice? Pick the tier yourself: `python check_hardware.py --tier cpu-only --apply`.
Or skip the script and copy the matching file from [`presets/`](../presets) to `.env`.

---

## 2. The four tiers

| Tier | Typical hardware | Speech model | AI model | Voice | Words appear after* |
|---|---|---|---|---|---|
| [**NVIDIA desktop**](#nvidia-desktop--8-gb-or-more) | RTX 3060 12 GB, 3070, 4060 Ti, 4070+ | `large-v3` | `qwen2.5:7b` | GPU | **≈1 s** (measured) |
| [**NVIDIA laptop**](#nvidia-laptop--4-to-7-gb) | RTX 3050, 3060/4050/4060 laptop | `medium` (`small` on 4 GB) | `qwen2.5:3b` | GPU | ≈1 s (estimate) |
| [**CPU only**](#cpu-only--no-graphics-card) | any laptop/desktop with built-in graphics | `small` (`base` on 8 GB RAM) | `qwen2.5:3b` (`gemma2:2b`) | CPU | ≈2–4 s (estimate) |
| [**AMD / Intel card**](#amd-radeon--intel-arc) | Radeon RX 6000–9000, Arc A/B | `small` | `qwen2.5:3b`, maybe `7b` | CPU | ≈2–4 s (estimate) |

\* For about 14 seconds of speech, in the *raw* modes (`F5`/`F7`). Polish and Translate
add the AI model's time on top — about 1–3 s on a GPU, several seconds on a CPU.

### NVIDIA desktop — 8 GB or more
[`presets/nvidia-desktop.env`](../presets/nvidia-desktop.env) — everything on the graphics card.

- **Install:** the CUDA build of torch *before* the rest (see [INSTALL.md](INSTALL.md#4-install-the-python-packages)),
  and keep the two `nvidia-` lines in `requirements.txt`.
- **Graphics memory** (measured on a 12 GB RTX 4070): speech 3.9 GB + voice 1.1 GB +
  `qwen2.5:7b` ≈ 5.5 GB ≈ **10.5 GB**. Fits 12 GB with room to spare.
- **8–10 GB cards:** the checker switches `WHISPER_COMPUTE_TYPE` to `int8_float16`,
  which halves the speech model to **2.0 GB** for about 0.2 s more per clip (measured).
- **16 GB and up:** room for a bigger AI model, e.g. `qwen2.5:14b` (≈9 GB) for better
  Polish and Translate.

### NVIDIA laptop — 4 to 7 GB
[`presets/nvidia-laptop.env`](../presets/nvidia-laptop.env) — everything on the GPU, with smaller models.

- **Install:** same as the desktop tier (CUDA torch first).
- **Graphics memory** (estimate): `medium` in `int8_float16` ≈ 1 GB + voice 1.1 GB +
  `qwen2.5:3b` ≈ 2.5 GB ≈ **4.6 GB**. On 4–5 GB cards the checker picks `small`
  (≈0.4 GB). If the AI model still does not fit, Ollama puts part of it on the CPU —
  slower Polish, nothing breaks.
- **Plug the charger in.** Laptop GPUs slow down a lot on battery.

### CPU only — no graphics card
[`presets/cpu-only.env`](../presets/cpu-only.env) — the most common laptop. Also the
tier for built-in graphics (Intel UHD / Iris Xe, AMD "Radeon Graphics"), which share
system memory and are no faster than the CPU for these models.

- **Install:** delete the two `nvidia-` lines from `requirements.txt` (saves 1.2 GB).
- **Speed** (measured on an 8-core i7-11700): `large-v3` needs 12.8 s per 14 s clip on
  the CPU — too slow. `small` is about a sixth of its size (estimate: 2–3 s). The voice
  runs at 3× real time: it starts about a second after you press `F4`.
- **8 GB of RAM:** the checker picks `base` and `gemma2:2b`, and the raw modes
  (`F5`/`F7`) are the comfortable ones.
- **Heat:** see [§6](#6-laptops-heat-battery-and-noise).
- The complete beginner walkthrough for this tier: [SETUP-CPU-LAPTOP.md](SETUP-CPU-LAPTOP.md).

### AMD Radeon / Intel Arc
[`presets/amd-intel-gpu.env`](../presets/amd-intel-gpu.env)

- **Speech and voice run on the CPU**, like the CPU-only tier. On Windows, the speech
  engine (CTranslate2) and the voice (PyTorch) can only use NVIDIA cards.
- **Ollama can use your card** — many Radeon cards are supported on Windows. After a
  Polish, run `ollama ps`: if it says `100% GPU` and your card has 8 GB or more, try
  `OLLAMA_MODEL_NAME="qwen2.5:7b"` for better Polish and Translate at no extra wait.
- **Install:** as the CPU-only tier (delete the two `nvidia-` lines).

---

## 3. What we measured

On one PC — **RTX 4070 (12 GB), Intel i7-11700 (8 cores), 32 GB RAM** — with a
14.2-second English dictation clip, speech model `large-v3`:

| Speech model runs on | Graphics memory | Time for the clip | Mistakes |
|---|---|---|---|
| GPU, `float16` | 3.9 GB | 0.9 s | none |
| GPU, `int8_float16` | 2.0 GB | 1.1 s | none |
| CPU, `int8`, 16 threads | — | 12.8 s | none |

| Voice (Kokoro) runs on | Graphics memory | Time for 14 s of speech | Speed |
|---|---|---|---|
| GPU | 1.1 GB | 0.2 s | 70× real time |
| CPU | — | 4.8 s | 3× real time |

The clip was clear, synthesised speech, so "no mistakes" means the lower precision did
not *hurt* here — not that every model is equally accurate on real voices. Everything
marked *estimate* elsewhere in this guide is scaled from these numbers by model size.

---

## 4. The settings that matter

All of them live in `.env` (restart the engine after changing it). Full reference:
[CONFIGURATION.md](../CONFIGURATION.md).

### Speech model — `WHISPER_MODEL_NAME`
The biggest single lever. Bigger is more accurate, especially for **Arabic**, and slower.

| Model | Download | GPU memory (`float16` / `int8_float16`) | CPU time per 14 s clip | Accuracy |
|---|---|---|---|---|
| `tiny` | 75 MB | ≈0.2 / 0.1 GB | < 1 s | rough; poor Arabic |
| `base` | 145 MB | ≈0.3 / 0.15 GB | ≈1 s | usable English, weak Arabic |
| `small` | 480 MB | ≈0.7 / 0.35 GB | ≈2–3 s | good English, fair Arabic |
| `medium` | 1.5 GB | ≈2 / 1 GB | ≈6 s | very good, good Arabic |
| `large-v3` | 3 GB | **3.9 / 2.0 GB** | **12.8 s** | best — the default |

Bold = measured; the rest are estimates from model size. Downloads happen once, on
the first start after you change the setting.

### Where the speech model runs — `WHISPER_DEVICE` and `WHISPER_COMPUTE_TYPE`

| Setting | Values | When to change it |
|---|---|---|
| `WHISPER_DEVICE` | `auto` (NVIDIA GPU, else CPU) · `cpu` | `cpu` on machines without an NVIDIA card skips a pointless GPU attempt at start-up. Also useful to leave all graphics memory to a big AI model. |
| `WHISPER_COMPUTE_TYPE` | `float16` · `int8_float16` · `int8` | `int8_float16` halves graphics memory (measured 3.9 → 2.0 GB) for ≈0.2 s per clip. Use it on cards under 11 GB. The CPU always uses `int8`. |

### AI model — `OLLAMA_MODEL_NAME`
Used only by Polish (`F6`/`F8`), Translate (`F9`/`F10`), fix-line (`Shift+F3`),
vocabulary clean-up (`Shift+F1`) and the reader's optional Smart Cleaning. The raw
modes never touch it. Download it first: `ollama pull <name>`.

| Model | Download | Good for |
|---|---|---|
| `gemma2:2b` | ≈1.6 GB | 8 GB RAM machines; basic Polish |
| `qwen2.5:3b` | ≈1.9 GB | laptops; good English and Arabic |
| `qwen2.5:7b` | 4.7 GB | 8 GB+ graphics cards; clearly better Translate |
| `qwen2.5:14b` | ≈9 GB | 16 GB+ cards |

Leave `OLLAMA_MODEL_NAME` blank and the engine uses whichever model Ollama lists first
— pinning it avoids surprises.

### Voice — `READER_DEVICE` and batch sizes

| Setting | Default | When to change it |
|---|---|---|
| `READER_DEVICE` | `auto` | `cpu` on machines without an NVIDIA card (the presets do this). |
| `READER_FIRST_BATCH_CHARS` | `120` | On a CPU, lower (e.g. `80`) makes the voice start sooner; higher reads more smoothly. |
| `READER_BATCH_CHARS` | `300` | Rarely worth touching. |
| `READER_SMART_MODE` | `False` | `True` sends text through the AI model before reading — only worth it on a fast AI model. |

---

## 5. Is it tuned right? Read the signs

**Where to look**
- The console prints how long each clip took: `📝 Raw (1.2s): …`
- `flow_debug.log` has the same for every dictation: `…, 1.21s for 14.2s of audio): …`
- The start-up banner shows where the speech model loaded, e.g.
  `Speech to text: [Whisper large-v3 · GPU · float16]`.
- `ollama ps` (in PowerShell, right after a Polish) shows whether the AI model sits on
  the GPU or the CPU.
- `nvidia-smi` shows how much graphics memory is in use.

**Symptom → fix**

| You see | Likely cause | Fix |
|---|---|---|
| Words take more than ~3 s after you stop | speech model too big for the device | one size smaller (`large-v3` → `medium` → `small` → `base`) |
| Banner says `CPU · int8` on an NVIDIA PC | CUDA libraries or driver missing | `flow_debug.log` says why; reinstall `nvidia-cublas-cu12` / `nvidia-cudnn-cu12`, update the NVIDIA driver |
| Polish / Translate slow, `ollama ps` shows `CPU` | AI model does not fit the card | smaller `OLLAMA_MODEL_NAME`, or `WHISPER_COMPUTE_TYPE="int8_float16"` to free memory |
| Voice takes several seconds to start | voice on the CPU | normal on CPU; lower `READER_FIRST_BATCH_CHARS`, read a paragraph at a time |
| `reader_debug.log` says "CPU-only build of torch" on an NVIDIA PC | the CPU torch was installed | reinstall torch with the CUDA command in [INSTALL.md](INSTALL.md#4-install-the-python-packages) |
| Arabic comes out wrong, English is fine | speech model too small for Arabic | `medium` or `large-v3` — Arabic gains the most from size |
| Whole PC sluggish while dictating | out of RAM | smaller speech and AI models; close other heavy apps |
| Random phrases like "Thanks for watching!" from silence | Whisper hallucinating on near-silence | speak closer to the mic; stop recording right after you finish speaking |

---

## 6. Laptops: heat, battery and noise

- The models only work for the few seconds after each dictation or while preparing
  speech. The rest of the time the engine is idle.
- The **raw modes** (`F5` English, `F7` Arabic) skip the AI model entirely — the
  single biggest saving. Use Polish and Translate when you need them.
- **Plug in** for best speed; on battery, Windows and the GPU both slow down.
- Work on a hard surface so the vents can breathe.
- Still too hot? One speech-model size down, and `gemma2:2b` for the AI model.

---

## 7. What is not supported

- **macOS and Linux** — the engine hooks the Windows keyboard and speaker APIs.
- **Windows on ARM** (Snapdragon laptops) — untested; the speech engine may not install.
- **GPU speech on AMD/Intel cards** — not on Windows, today. They still work, on the CPU.

---

*The numbers in this guide come from one machine and one clip. If you measure a
different card, the lines from `flow_debug.log` are exactly what is needed to extend
the tables.*
