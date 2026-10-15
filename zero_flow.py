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

--------------------------------------------------------------------------------
WHY A CHILD PROCESS AND NOT A THREAD
--------------------------------------------------------------------------------
An earlier version really did host both halves in one process. It worked, but it had
to force the voice model onto the CPU: torch 2.5.1+cu121 bundles cuDNN 9.1 while
CTranslate2 (Whisper) needs the pip-installed cuDNN 9.23, Windows loads exactly one
DLL per base name per process, and whichever initialises CUDA second gets the wrong
one and **segfaults** — in either load order, with no exception to catch. That cost
about 2 seconds of silence before the first spoken word.

Separate processes have separate DLL namespaces, so the conflict simply does not
arise: Whisper keeps the GPU here, Kokoro gets the GPU over there, and time to first
word drops to ~0.2 s. A crash in either half also stops being fatal to the other.

The two coordinate over named Windows objects in `zeroflow/signals.py` — the microphone
interlock and the clipboard mutex both work across the process boundary.

Both halves still run standalone: `local_flow.py` and `python -m reader`.
The code lives in the zeroflow/ package (zeroflow/supervisor.py).
"""
import sys

from zeroflow import supervisor

if __name__ == "__main__":
    sys.exit(supervisor.run())
