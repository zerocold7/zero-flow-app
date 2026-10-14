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

All of them are best-effort: if the signalling layer is unavailable the helpers
degrade to "nothing is recording, nobody is listening", and the clipboard lock to an
in-process lock — which is exactly how the two halves behaved before this module
existed.
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


def exit_requested():
    """True if someone has already asked the engine to shut down."""
    return wait_for_exit(0)


# =====================================================================
# ONE COPY AT A TIME
# =====================================================================
ERROR_ALREADY_EXISTS = 183
_instance_handles = {}


def claim_single_instance(role):
    """Claim `role` ("dictation", "reader") for this process. False if another
    process — or an earlier call here — already holds it.

    Two engines both answered every hotkey, so every dictation was pasted twice.
    The claim is a named mutex that Windows drops when the process ends, however it
    ends, so a crashed engine never blocks the next start."""
    if _kernel32 is None:
        return True                              # no way to tell: behave as before
    if role in _instance_handles:
        return False
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    handle = k32.CreateMutexW(None, False, f"Local\\ZeroFlow.instance.{role}")
    if not handle:
        logging.warning(f"Single-instance check unavailable for '{role}'.")
        return True
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        k32.CloseHandle(ctypes.c_void_p(handle))
        return False
    _instance_handles[role] = handle             # held until this process ends
    return True


# =====================================================================
# CHILD PROCESSES DIE WITH THE ENGINE
# =====================================================================
class _BasicLimits(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", ctypes.c_uint32),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", ctypes.c_uint32),
                ("SchedulingClass", ctypes.c_uint32)]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimits),
                ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_job = None


def bind_child_to_this_process(process):
    """Make Windows end `process` (a subprocess.Popen) when this process ends — on a
    crash or an End task too, when no clean-up code of ours gets to run.

    A Job Object with "kill on close": this process holds the only handle to the job,
    and Windows closes it, killing the job's processes, the moment this one is gone.
    Without it a crashed engine left the reader running on its own. Best effort:
    returns False if the child could not be bound."""
    global _job
    if _kernel32 is None:
        return False
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = ctypes.c_void_p
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        k32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                                ctypes.c_void_p, ctypes.c_uint32]
        k32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        if _job is None:
            job = k32.CreateJobObjectW(None, None)
            limits = _ExtendedLimits()
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not job or not k32.SetInformationJobObject(
                    job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                    ctypes.byref(limits), ctypes.sizeof(limits)):
                raise OSError(ctypes.get_last_error(), "could not set up the job")
            _job = job                           # never closed: closing it kills the child
        if not k32.AssignProcessToJobObject(_job, int(process._handle)):
            raise OSError(ctypes.get_last_error(), "could not add the process to the job")
        return True
    except Exception as e:
        logging.warning(f"Could not tie the child process to the engine's lifetime: {e}")
        return False


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
            if _clipboard_handle:
                return
            # NULL, not an exception, is how CreateMutexW fails. Left as-is, every
            # wait on it would fail at once and be reported as a timeout.
            _clipboard_handle = None
            logging.warning("Cross-process clipboard lock unavailable (CreateMutexW failed); "
                            "falling back to an in-process lock.")
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
