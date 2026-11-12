# Phase 7 gate: a clean PC in Windows Sandbox

The last check of Phase 7: the CPU-light installer on a fresh Windows that has never seen Zero- Flow. The Sandbox has no graphics card, so the GPU edition's CUDA path is checked on Zero's PC instead (last section).

## Before the first run (once)

Windows Sandbox is a Windows feature, off on Zero's PC. Two buttons on the Desktop switch it, and Zero presses them (scripts in `F:\Tools\Windows Sandbox`):

- **Sandbox ON**, first press: notes what is on now, turns on Windows Sandbox (admin prompt), and offers to restart. Press it again after the restart to open `packaging\sandbox.wsb`.
- **Sandbox OFF**, after the test: turns off only what ON turned on, and offers to restart. Press it again after the restart: it lists what the Sandbox left on C (only items that were not there before ON) and asks before deleting them, then asks about the test builds in `dist` and `build`.

The installers must be in `dist\installer` (`tools\build_installer.py cpu`). The Sandbox starts with the installer folder open: read-only, 8 GB of memory (like a typical new user's PC), network, microphone and clipboard on.

Everything in the Sandbox is thrown away when it closes, including the models it downloads. While it runs, it uses space on C. A full run fits in the 57 GB free.

## The run (CPU-light)

Checks marked *PS* run in PowerShell inside the Sandbox.

| # | Do | Expect | Result |
|---|---|---|---|
| 1 | Run `ZeroFlow-<version>-cpu-setup.exe`, English | No admin prompt. Installs to `%LOCALAPPDATA%\Programs\ZeroFlow`. The licence and notices are in that folder. | |
| 2 | Finish with "Launch Zero- Flow" | The first-run wizard opens. | |
| 3 | Go through the wizard | The models download, then the tray icon appears. Its tooltip shows the version and "Active". | |
| 4 | Dictate a sentence in Raw mode | The text is typed, and the log says it ran on the CPU. | |
| 5 | Select text, press F4 | The Reader speaks it, on the CPU. | |
| 6 | Task Manager (Details tab) in the Sandbox: dictate, then F4 on a long paragraph | Note the peak memory of the two ZeroFlow.exe processes and of the whole Sandbox. Nothing fails with 8 GB. Phase 8 uses this number as the stated minimum. | |
| 7 | Settings: change one setting, Save | The engine restarts with the new value. The window shows the version. | |
| 8 | Settings: turn on Start with Windows | *PS* `reg query HKCU\Software\Microsoft\Windows\CurrentVersion\Run` shows the installed ZeroFlow.exe. | |
| 9 | Save an API key (any text) in Settings | *PS* `cmdkey /list \| findstr ZeroFlow` shows it. | |
| 10 | Start the uninstaller while the engine runs | It says Zero- Flow is running and waits until it is closed. | |
| 11 | Close the engine, uninstall, answer **No** | The program folder and the Run key are gone. `%APPDATA%\ZeroFlow` and the API key stay. | |
| 12 | Run the setup again, Arabic | The setup's pages are in Arabic. The engine starts without the wizard, with step 7's setting. | |
| 13 | Uninstall, Arabic question, answer **Yes** | `%APPDATA%\ZeroFlow`, `%LOCALAPPDATA%\ZeroFlow` and the program folder are gone. `cmdkey /list` shows no ZeroFlow key. | |

Optional, if time allows: install the GPU edition over the CPU-light one. It should replace it (one entry under Installed apps). With no graphics card, the Reader falls back to the CPU.

If anything fails, use Copy diagnostics in Settings (the clipboard comes back to this PC), then close the Sandbox.

## On Zero's PC (GPU edition)

Here the installed program shares `%APPDATA%\ZeroFlow` with the development copy. Answer **No** when uninstalling here: Yes deletes your real settings, vocabulary, history and API keys.

| # | Do | Expect | Result |
|---|---|---|---|
| G1 | Install `ZeroFlow-<version>-gpu-setup.exe` with the dev engine stopped | The engine starts with your settings, no wizard. | |
| G2 | Dictate, then F4 | The log says CUDA for both. | |
| G3 | Uninstall, answer **No** | The program folder is gone. Your settings stay. | |

The gate passes when every row passes. Then Phase 7 stops: no merge, tag or push.

## After the test

Press **Sandbox OFF**, restart, then press it again to clean up (see the top of this page).
