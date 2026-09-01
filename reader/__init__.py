"""
Zero- Flow Engine — reader (text → speech).

The other half of the engine: highlight text anywhere in Windows, press the read
hotkey, and Kokoro speaks it aloud. Dictation (speech → text) lives in
`local_flow.py`; both halves share `flow_core.py`, `personas.py` and `engine_ui.py`.

Run it with:  python -m reader        (or Launch_Reader.bat)
"""
import flow_core

# Attach the reader's own rotating log before anything in the package logs a line.
# Separate from flow_debug.log on purpose — see flow_core.init_logging.
flow_core.init_logging("reader")
