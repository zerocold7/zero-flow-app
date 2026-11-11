"""Start Zero- Flow with no console window: double-click this file.

It hands over to the project's own pythonw (venv\Scripts\pythonw.exe), so the Engine
runs on the packages installed for it whichever Python Windows opens .pyw files with.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHONW = os.path.join(ROOT, "venv", "Scripts", "pythonw.exe")
python = VENV_PYTHONW if os.path.exists(VENV_PYTHONW) else sys.executable
subprocess.Popen([python, os.path.join(ROOT, "zero_flow.py"), *sys.argv[1:]], cwd=ROOT,
                 creationflags=0x00000008)          # DETACHED_PROCESS
