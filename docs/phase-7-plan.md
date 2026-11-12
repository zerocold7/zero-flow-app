# Phase 7 plan: packaging and installer

Branch `packaging`. Decisions so far: the GPU edition keeps CUDA torch (memory, 2026-11-04 and 2026-11-12); the installer ships espeak-ng, so Zero- Flow is published as open source (ADR 0003).

## What was measured (2026-11-12)

| What | Result | Script |
|---|---|---|
| One-folder build, GPU | 4.5 GB, 8,232 files | `packaging/zeroflow.spec` (draft) |
| One-folder build, CPU-light | 1.1 GB (CUDA files filtered out) | same |
| Start to "Whisper model active" | source 5.6 s warm (CUDA); builds 10 s (on the CPU: see 3) | `tools/measure_start.py` |
| First-run download | NVIDIA desktop 8.6 GB, NVIDIA laptop 4.5 GB, CPU / AMD-Intel 5.6 GB | `tools/measure_packaging.py` |
| Reader, GPU vs CPU | first sound 0.10 s vs 0.9 s | `tools/bench/measure_load.py` |
| Whisper on torch's CUDA DLLs only | works, 3.9 s load + warm-up | `tools/measure_cuda_from_torch.py` |
| Licences | 5 GPL parts: phonemizer-fork, espeak-ng (kept, ADR 0003); x264, x265, postproc in PyAV's FFmpeg (removed, see 4) | `tools/licence_audit.py` |
| Words the Reader hands to espeak | 2.9% of the project's English docs | `tools/measure_espeak_use.py` |

## Work, in order (each with its tests first)

**1. Children in a build** (`zeroflow/frozen.py`, `tests/test_frozen.py`)
In a build `sys.executable` is `ZeroFlow.exe`, so the five `sys.executable` launches would start a second Engine. Children become `ZeroFlow.exe --child reader|fetch|ai-check`; `zero_flow.py` hands them to the module before it imports the supervisor. Restart and Start with Windows run the exe itself. From source nothing changes. A windowed build sets `sys.stdout` to None even when a pipe was passed, and the AI test reads its answer from that pipe, so a child reopens its standard streams first.

**2. The AI runtime leaves the program folder** (`paths.runtime_dir`)
In a build it goes to `%LOCALAPPDATA%\ZeroFlow\runtime`; from source it stays in `runtime\` (your copy is not moved).

**3. Whisper finds CUDA in a build** (`frozen.cuda_dll_dirs`)
The draft GPU build fell back to the CPU: `stt` looks for `nvidia\*\bin` on `sys.path`, and a build has none. In a build it adds `_internal\torch\lib`, measured to work. The nvidia-cublas/cudnn packages are not shipped, saving 1.9 GB compared with shipping both.

**4. The build file** (`packaging/zeroflow.spec`, `tools/check_build.py`)
- `av` replaced by an empty module: only `faster_whisper/audio.py` imports it, for audio files, and Zero- Flow hands Whisper numpy arrays. That removes the GPL FFmpeg parts and 71 MB.
- `num2words` (LGPL) is shipped as loose `.py` files, so it can be replaced.
- `LICENSE.txt` and `THIRD-PARTY-NOTICES.txt` go in the program folder.
- CPU-light is built from a second venv holding the CPU-only torch (`F:\Claude Project\zero-flow-app\venv-cpu`, about 1.5 GB, **a download: I ask first**), instead of filtering DLLs out of the CUDA build.
- `tools/check_build.py` fails a build that has GPL FFmpeg, development tools, CUDA in the CPU edition, the nvidia packages twice, or is missing espeak-ng, the spaCy model, presets, notices or num2words.

**5. Version shown** (`tests/test_packaging.py`)
`zeroflow.__version__` is the one source: in the tray tooltip, a label in the Settings window, and the installer.

**6. Update check, opt-in** (`zeroflow/updates.py`, `tests/test_updates.py`)
New setting "Check for updates", default **off**: Main tab, in the settings table. When on, one request to GitHub Releases at start (`/releases/latest`, 5 s timeout, User-Agent `ZeroFlow/<version>`), and a notification with the release page when a newer version is out. Nothing is downloaded or installed. Only github.com links are opened. The repository name is a constant until Phase 8 creates the public repo.

**7. Uninstaller that asks** (`zeroflow/uninstall.py`, `tests/test_uninstall.py`)
Inno Setup asks "Also delete your settings, vocabulary, history, logs and downloaded models?", with **No** as the default.
- **No:** `--remove-startup` removes only the Start-with-Windows entry.
- **Yes:** `--remove-data` also removes `%APPDATA%\ZeroFlow`, `%LOCALAPPDATA%\ZeroFlow` and every `ZeroFlow:*` API key.
- A models folder you chose (your `F:\HuggingFace`) is never deleted, only reported as kept.

**8. Inno Setup script** (`packaging/zeroflow.iss`, `tools/build_installer.py`)
- Per-user install (`PrivilegesRequired=lowest`, no admin prompt), one AppId for both editions, and AppMutex on the Engine's single-instance lock.
- `build_installer.py` runs four steps in order: PyInstaller, then `check_build`, then the licence audit, then ISCC. It stops on any GPL part other than the two ADR 0003 accepted.
- **Inno Setup 6 is an install: I ask first.** Proposed place: `F:\Tools\Inno Setup 6`.

**9. Fix found on the way**
`tools/bench/measure_load.py` "reader-cpu" set `READER_DEVICE` in the environment, which ADR 0002 ignores, so it measured the GPU. It now writes a temporary settings file.

**10. Clean-PC gate in Windows Sandbox** (`packaging/sandbox.wsb`)
The installer folder is mapped read-only. The run: install, the wizard, first run's downloads, a dictation (Raw, CPU: the Sandbox has no NVIDIA), F4, Settings save → restart, Start with Windows, uninstall both ways. The CPU-light edition is the one the Sandbox can test fully; the GPU edition's CUDA path is checked on your PC. **I stop there: no merge, tag or push.**

## Status (2026-11-12, step 9)

Approved: the plan, the tests, per-user install, and the second venv (`venv-cpu`, created).

| Step | State |
|---|---|
| 1 Children in a build | done |
| 2 AI runtime folder | done |
| 3 CUDA in a build | done |
| 4 Build file, check_build, av stand-in | done; both editions built and started with the Reader child |
| 5 Version shown | done |
| 6 Update check | done |
| 7 Uninstaller | done |
| 8 Inno Setup script, build script | done. Inno Setup 6.7.4 is installed per user at `F:\Tools\Inno Setup 6`, and `Arabic.isl` ships with it. Installers: CPU-light 0.215 GB, GPU 1.660 GB (under the ~4 GB single-file limit, so no disk spanning). ISCC gave 0 warnings. The build runs the licence audit before `check_build`, because `check_build` needs the notices the audit writes. Both installers are unsigned, so SmartScreen warns about them (a Phase 8 question). |
| 9 measure_load fix | done, waiting for Zero's OK |
| 10 Sandbox gate | `packaging/sandbox.wsb` and the checklist `docs/sandbox-gate.md` are ready. The run waits for Zero to turn on Windows Sandbox (an admin step and a restart). Stop there: no merge, tag or push. |

Numbers at the end of step 4: 709 passed, 13 failed (all steps 5–9), 11 skipped, with `--ignore=tests/test_updates.py --ignore=tests/test_uninstall.py` (their import errors stop pytest's whole run until the modules exist). 231 mutation guards, all caught.

Final builds (same spec, `dist/` emptied first):

| | CPU-light, from `venv-cpu` | GPU, from `venv` |
|---|---|---|
| Size before compression | 951 MB | 4.4 GB |
| Packages shipped | 109 | 109 |
| GPL parts | espeak-ng 1.52.0, phonemizer-fork 3.3.2 | the same |
| Dictation ready, warm | 9.4 s (CPU) | 5.5 s (CUDA) |
| Reader ready, warm | 20.0 s (CPU) | 16.0 s (CUDA) |
| Processes | 2 | 2 |

How a build is made today (step 8's script will do this):

    rmdir /s dist\<edition>
    <venv>\Scripts\pyinstaller packaging\zeroflow.spec --noconfirm --distpath dist\<edition> --workpath build\<edition>
    <venv>\Scripts\python tools\licence_audit.py build\<edition>\zeroflow
    copy LICENSE dist\<edition>\ZeroFlow\LICENSE.txt
    copy THIRD-PARTY-NOTICES.txt dist\<edition>\ZeroFlow\
    <venv>\Scripts\python tools\check_build.py <edition>

`<venv>` is `venv` for gpu and `venv-cpu` for cpu. The audit must run in the same venv as the build. `THIRD-PARTY-NOTICES.txt` is generated per edition and not committed.

## Learned on the way (for steps 5–10)

- Your dev venv holds packages the program does not need (pytest, soundfile, pip-audit's tomli, pystray/reportlab's pillow). `test_the_gpu_build_ships_only_what_requirements_pull_in` catches any that leak in; the spec's `LEFTOVERS` excludes them.
- A failed PyInstaller run leaves the previous `dist\` in place, and check_build passes it. Empty `dist\<edition>` first and stop on PyInstaller's exit code.
- PySide6 inspects every module imported after it. A stand-in module must raise AttributeError, never anything else.
- Backslashes in heredocs through the Bash tool get eaten (`\n`, `\r`, `\b`). Write such text with the Write or Edit tool.
- The mutation tool also looks in `tools/check_build.py`, `tools/licence_audit.py` and `packaging/stubs/av.py`. After an edit, update any anchor that shows SKIPPED.
