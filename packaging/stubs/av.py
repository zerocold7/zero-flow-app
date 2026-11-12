"""Stand-in for PyAV in the installed program (packaging/zeroflow.spec).

faster-whisper imports `av` at load time only to decode audio *files*. Zero- Flow hands
Whisper the recording as a numpy array, so it never decodes one. PyAV's wheel carries a
GPL build of FFmpeg (x264, x265, postproc) and 71 MB; this module replaces it.

Every attribute is missing, with AttributeError as Python expects: PySide6 inspects each
module imported after it (it asks for `__wrapped__`), and hasattr() must say False, not
raise. A real use fails with a message that says why.
"""


def __getattr__(name):
    raise AttributeError(f"av.{name}: Zero- Flow does not decode audio files "
                         "(PyAV is not part of the installed program)")
