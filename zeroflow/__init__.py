"""
Zero- Flow Engine — private, offline voice dictation and read-aloud for Windows.

    paths, settings, logs     where files live, .env, the debug and crash logs
    signals                   named Windows objects shared by the two processes
    ui, personas              console/toasts/tray/tones; prompts, macros, vocabulary seed
    vocabulary, history       the learned-word list and the dictation history
    text.language, .macros    language checks; spoken commands and punctuation
    llm                       the AI model client (Ollama today)
    stt                       Whisper: loading, transcription, invented endings
    capture, clipboard        one recording's audio; paste and copy through the clipboard
    hotkeys, engine           key helpers; the dictation pipeline itself
    supervisor                the whole engine: dictation here, the reader as a child

Entry points stay at the top of the project: local_flow.py, zero_flow.py, and
`python -m reader`. Nothing here imports torch or the voice model; only stt imports
faster-whisper, so the reader process never loads Whisper's CUDA libraries.
"""
__version__ = "2.0.0-alpha.3"
