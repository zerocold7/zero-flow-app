"""
Cross-process signals between the two halves of the engine.

Flow (dictation) and Reader (speech) run as separate processes, so they cannot share
Python state. These are Windows named events in the per-session "Local" namespace:
creating one is free, setting one that nobody is listening to is a no-op, and each
half works perfectly well when the other is not running at all.

Two signals, both owned by the dictation half:

    RECORDING       Set while the microphone is open. The reader refuses to speak
                    while it is set — otherwise the mic picks up the synthetic voice
                    and Whisper faithfully transcribes the engine talking to itself.
    SILENCE_READER  Pulsed when a recording starts, asking the reader to stop
                    speaking immediately.

Both are best-effort: if the signalling layer is unavailable the helpers degrade to
"nothing is recording, nobody is listening", which is exactly how the two halves
behaved before this module existed.
"""
import ctypes
import logging

WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
INFINITE = 0xFFFFFFFF

_RECORDING_NAME = "Local\\ZeroFlow.recording"
_SILENCE_NAME = "Local\\ZeroFlow.silence_reader"

try:
    _kernel32 = ctypes.windll.kernel32
    _kernel32.CreateEventW.restype = ctypes.c_void_p
    _kernel32.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_bool,
                                       ctypes.c_wchar_p]
    _kernel32.SetEvent.argtypes = [ctypes.c_void_p]
    _kernel32.ResetEvent.argtypes = [ctypes.c_void_p]
    _kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
except Exception:                                # not Windows, or no ctypes
    _kernel32 = None

_handles = {}


def _event(name, manual_reset):
    """Open the named event, creating it if this is the first process to ask.
    Returns None if signalling is unavailable, which every caller treats as 'off'."""
    if _kernel32 is None:
        return None
    if name not in _handles:
        try:
            _handles[name] = _kernel32.CreateEventW(None, manual_reset, False, name)
        except Exception as e:
            logging.warning(f"Cross-process signalling unavailable: {e}")
            _handles[name] = None
    return _handles[name]


def available():
    """False when cross-process signalling could not be set up — callers should fall
    back to their old, un-coordinated behaviour rather than busy-waiting."""
    return _kernel32 is not None


def set_recording(state):
    """Flow: announce that the microphone is open (or no longer is)."""
    handle = _event(_RECORDING_NAME, manual_reset=True)
    if not handle:
        return
    if state:
        _kernel32.SetEvent(handle)
    else:
        _kernel32.ResetEvent(handle)


def is_recording():
    """Reader: True while the dictation half has the microphone open."""
    handle = _event(_RECORDING_NAME, manual_reset=True)
    if not handle:
        return False
    return _kernel32.WaitForSingleObject(handle, 0) == WAIT_OBJECT_0


def request_reader_silence():
    """Flow: ask the reader to stop speaking. Harmless if it isn't running."""
    handle = _event(_SILENCE_NAME, manual_reset=False)
    if handle:
        _kernel32.SetEvent(handle)


def wait_for_silence_request(timeout_ms=INFINITE):
    """Reader: block until Flow asks for silence. Returns False on timeout, and
    False forever if signalling is unavailable (the watcher thread then idles)."""
    handle = _event(_SILENCE_NAME, manual_reset=False)
    if not handle:
        return False
    return _kernel32.WaitForSingleObject(handle, timeout_ms) == WAIT_OBJECT_0
