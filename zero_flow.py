"""
Zero- Flow Engine — the whole engine in one window.

    F5-F10 / Shift+F1-F3   dictate, translate, fix a line   (speech -> text)
    F4                     read the highlighted text aloud   (text -> speech)
    Esc                    cancel a recording / silence the reader

This process runs the dictation half itself and launches the reader as a **child
process**. The child is started without CREATE_NEW_CONSOLE, so Windows hands it this
process's console: its output appears in this window, and the pair looks like a single
program. The child owns the one tray icon, because every control in that menu toggles
state that lives inside the reader.

Why a child process and not a thread (Whisper and the voice cannot both use CUDA in
one process), and how the two coordinate: ARCHITECTURE.md §1 and §12.

Both halves still run standalone: `local_flow.py` and `python -m reader`.
The code lives in the zeroflow/ package (zeroflow/supervisor.py).
"""
import sys

from zeroflow import supervisor

if __name__ == "__main__":
    sys.exit(supervisor.run())
