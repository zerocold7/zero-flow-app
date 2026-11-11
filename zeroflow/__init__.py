"""
Zero- Flow Engine — private, offline voice dictation and read-aloud for Windows.

    paths, settings, logs     where files live, settings.json, the debug and crash logs
    signals                   named Windows objects shared by the two processes
    ui, personas              console/toasts/tray/tones; prompts, macros, vocabulary seed
    vocabulary, history       the learned-word list and the dictation history
    text.language, .macros    language checks; spoken commands and punctuation
    llm                       the AI model: built in, Ollama, OpenAI-format or Claude
    stt                       Whisper: loading, transcription, invented endings
    capture, clipboard        one recording's audio; paste and copy through the clipboard
    hotkeys, engine           key helpers; the dictation pipeline itself
    supervisor, app           the whole engine: dictation here, the reader as a child;
                              the Qt tray, overlay and Settings window

Entry points stay at the top of the project: zero_flow.py (started by Zero_Flow.pyw),
and `python -m reader`, which only the Engine runs. Nothing here imports torch or the voice model; only stt imports
faster-whisper, so the reader process never loads Whisper's CUDA libraries.
"""
import os as _os
import sys as _sys

# Under pythonw there is no console and sys.stdout is None: anything that prints would
# crash. Point both at the null device (ui.print_banner also skips itself then).
for _name in ("stdout", "stderr"):
    if getattr(_sys, _name) is None:
        setattr(_sys, _name, open(_os.devnull, "w", encoding="utf-8"))

__version__ = "2.0.0-alpha.9"
