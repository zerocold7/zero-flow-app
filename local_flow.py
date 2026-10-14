"""
Zero- Flow Engine — the dictation half on its own (Launch_Flow.bat).

    F5-F10    dictate (English / Arabic, raw / polish) and translate
    Shift+F1-F3, Esc    vocabulary clean-up, clear logs, fix a line, cancel

For dictation and read-aloud together, run zero_flow.py (Launch_Zero.bat) instead.
The code lives in the zeroflow/ package; the pipeline itself is zeroflow/engine.py.
"""
import sys

from zeroflow import engine

if __name__ == "__main__":
    sys.exit(engine.run())
