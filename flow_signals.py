"""
Cross-process signals between the two halves of the engine.

Flow (dictation) and Reader (speech) run as separate processes, so they cannot share
Python state. These are Windows named events in the per-session "Local" namespace:
creating one is free, setting one that nobody is listening to is a no-op, and each
half works perfectly well when the other is not running at all.

Three signals and one lock:

    RECORDING       Set by Flow while the microphone is open. The reader refuses to
                    speak while it is set — otherwise the mic picks up the synthetic
                    voice and Whisper transcribes the engine talking to itself.
    SILENCE_READER  Pulsed by Flow when a recording starts, asking the reader to stop
                    speaking immediately.
    EXIT            Set by whichever half the user quits from. Under `zero_flow.py`
                    the reader owns the tray icon, so "Exit Engine" is a child-process
                    event that the parent has to hear about.
    CLIPBOARD       A named mutex, not an event. Both halves drive the clipboard —
                    the reader copies a selection, Flow pastes and restores — and each
                    sequence has to be atomic against the other. A threading lock
                    cannot do this across two processes.

Both are best-effort: if the signalling layer is unavailable the helpers degrade to
"nothing is recording, nobody is listening", which is exactly how the two halves
behaved before this module existed.
"""
import ctypes
import logging

WAIT_OBJECT_0 = 0x00000000
WAIT_ABANDONED = 0x00000080
WAIT_TIMEOUT = 0x00000102
INFINITE = 0xFFFFFFFF

_RECORDING_NAME = "Local\\ZeroFlow.recording"
_SILENCE_NAME = "Local\\ZeroFlow.silence_reader"
_EXIT_NAME = "Local\\ZeroFlow.exit"
_CLIPBOARD_MUTEX_NAME = "Local\\ZeroFlow.clipboard"

try:
    _kernel32 = ctypes.windll.kernel32
    _kernel32.CreateEventW.restype = ctypes.c_void_p
    _kernel32.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_bool,
                                       ctypes.c_wchar_p]
    _kernel32.CreateMutexW.restype = ctypes.c_void_p
    _kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    _kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
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


def request_exit():
    """Ask the whole engine to shut down. Set by whichever half the user quit from."""
    handle = _event(_EXIT_NAME, manual_reset=True)
    if handle:
        _kernel32.SetEvent(handle)


def wait_for_exit(timeout_ms=INFINITE):
    """Block until someone calls request_exit(). False on timeout, and False forever
    when signalling is unavailable, so a watcher thread exits instead of spinning."""
    handle = _event(_EXIT_NAME, manual_reset=True)
    if not handle:
        return False
    return _kernel32.WaitForSingleObject(handle, timeout_ms) == WAIT_OBJECT_0


# =====================================================================
# CLIPBOARD MUTEX
# =====================================================================
# The mutex handle (or the in-process fallback) is shared by the whole process; the
# per-`with` state that says whether we actually acquired it is not, so each call to
# clipboard_lock() hands back its own small context manager.
_clipboard_handle = None
_clipboard_fallback = None


def _clipboard_primitive():
    global _clipboard_handle, _clipboard_fallback
    if _clipboard_handle is not None or _clipboard_fallback is not None:
        return
    if _kernel32 is not None:
        try:
            _clipboard_handle = _kernel32.CreateMutexW(None, False, _CLIPBOARD_MUTEX_NAME)
            return
        except Exception as e:
            logging.warning(f"Cross-process clipboard lock unavailable ({e}); "
                            f"falling back to an in-process lock.")
    import threading
    _clipboard_fallback = threading.RLock()


class _ClipboardLock:
    """One acquisition of the engine-wide clipboard lock.

    A Windows mutex is owned by a thread and is recursive — each acquire needs its own
    release — which matches the `threading.RLock` this replaced, so nesting behaves as
    it did. Without signalling it degrades to an in-process RLock: weaker, but exactly
    what the code did before this existed.
    """

    def __init__(self):
        self._acquired = False

    def __enter__(self):
        if _clipboard_fallback is not None:
            _clipboard_fallback.acquire()
            self._acquired = True
            return self
        # Bounded wait: the clipboard is only ever held for a few hundred milliseconds,
        # so a longer wait means the other half is wedged or gone. Carrying on without
        # the lock then beats freezing the hotkey forever. WAIT_ABANDONED (0x80) also
        # counts as acquired — it means the previous owner died holding it.
        result = _kernel32.WaitForSingleObject(_clipboard_handle, 5000)
        self._acquired = result in (WAIT_OBJECT_0, WAIT_ABANDONED)
        if not self._acquired:
            logging.warning("Clipboard lock timed out; proceeding without it.")
        return self

    def __exit__(self, *exc):
        if not self._acquired:                   # never release what we do not hold
            return False
        self._acquired = False
        if _clipboard_fallback is not None:
            _clipboard_fallback.release()
        else:
            try:
                _kernel32.ReleaseMutex(_clipboard_handle)
            except Exception:
                pass
        return False


def clipboard_lock():
    """The engine-wide clipboard lock: `with flow_signals.clipboard_lock(): ...`"""
    _clipboard_primitive()
    return _ClipboardLock()
