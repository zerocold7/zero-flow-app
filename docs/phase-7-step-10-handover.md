# Prompt for a new chat: Phase 7, step 10 (the Sandbox gate)

Use it after pressing **Sandbox ON** and restarting. Paste everything below the line.

---

Continue Phase 7 of Zero- Flow 2.0 on branch `packaging`. Do step 10: the clean-PC gate in Windows Sandbox. I have pressed Sandbox ON and restarted, so Windows Sandbox is on.

Read first, nothing else:
- `docs/sandbox-gate.md`: the run, 13 rows plus G1–G3 on my PC
- `docs/phase-7-plan.md`: step 10 and the Status table
- `packaging/sandbox.wsb`: 8 GB, no graphics card, installer folder read-only

State:
- Steps 1–9 are committed (af16224). Step 10's set-up is committed too (the last commit on `packaging`): `packaging/sandbox.wsb`, `docs/sandbox-gate.md` and this file. The gate run itself is not done.
- 793 passed, 11 skipped. 312 mutation guards, all caught. Ruff has 3 old errors in files Phase 7 did not touch.
- Installers are in `dist\installer`: CPU-light 0.215 GB, GPU 1.660 GB.
- Venvs: `venv\` (GPU, dev) and `venv-cpu\` (CPU-light builds).

How we work:
1. You can't see inside the Sandbox. I press **Sandbox ON** on the Desktop to open it, do each row, and paste what I see: text, PowerShell output, or Copy diagnostics (the clipboard comes back to this PC).
2. Give me one row at a time, in plain words: what to do and what to look for. Write each result in the Result column of `docs/sandbox-gate.md`.
3. Row 6: I read the peak memory from Task Manager. Record it; Phase 8 states it as the minimum.
4. When a row fails: name the cause first, then ask me before fixing. A fix follows the usual method: make the test fail, then pass, add a mutation guard and run `tools/mutation_check.py`, then run the full suite and ruff. Then rebuild with `venv-cpu\Scripts\python tools\build_installer.py cpu` and redo the rows the fix touches, in a fresh Sandbox.
5. After the Sandbox rows: G1–G3 on my PC with the GPU edition. On my PC, uninstall with **No** only, because Yes deletes my real settings and keys.
6. At the end: show me the filled checklist and the Status row for step 10, and remind me to press **Sandbox OFF** (restart, then press it again to clean up).

Do not commit without my OK. Do not merge, tag or push: Phase 7 stops at this gate.
