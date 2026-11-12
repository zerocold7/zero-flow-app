"""
Zero- Flow Engine — Dictation and the Reader in one program, with a tray icon.

    F5-F10 / Shift+F1-F3   dictate, translate, fix a line   (speech -> text)
    F4                     read the highlighted text aloud   (text -> speech)
    Esc                    cancel a recording / silence the reader

Start it with Zero_Flow.pyw (no console) or Launch_Zero.bat (a console, for development).
The tray icon holds everything else: Dictation on, Reader on, Settings, Exit.
This process runs Dictation and the Qt interface itself and launches the Reader as a
**child process** (ARCHITECTURE.md §1 and §12). The code lives in zeroflow/supervisor.py.

In the installed program this is ZeroFlow.exe, which also plays the child processes
(`ZeroFlow.exe --child reader`, zeroflow/frozen.py). A child is handed over before the
supervisor is imported, so it never loads Qt or claims the Engine's single-instance lock.
"""
import sys

from zeroflow import frozen

if __name__ == "__main__":
    if frozen.run_child(sys.argv):
        sys.exit(0)
    from zeroflow import supervisor
    sys.exit(supervisor.run())
