"""
Zero- Flow Engine — reader (text → speech).

The other half of the engine: highlight text anywhere in Windows, press the read
hotkey, and Kokoro speaks it aloud. Dictation (speech → text) lives in
`local_flow.py`; both halves share the zeroflow/ package.

Run it with:  python -m reader        (or Launch_Reader.bat)
"""
from zeroflow import settings  # noqa: F401  (reads .env before the reader's own settings)
from zeroflow.logs import init_logging

# Attach the reader's own rotating log before anything in the package logs a line.
# Separate from flow_debug.log on purpose — see zeroflow/logs.py.
init_logging("reader")
