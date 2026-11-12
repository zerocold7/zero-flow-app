"""The first-run wizard's logic, with no Qt: when it runs, what it recommends, what it
downloads, and its microphone and AI tests (the window is zeroflow/wizard.py).

**When it runs:** only when there is no settings file and nothing of this user's to
migrate. The old files sit in the program folder, which every Windows user shares, so a
file counts only when it belongs to the user starting Zero- Flow: a new account never
takes over another person's history, vocabulary or API key.

**Downloads** run in a child process (`python -m zeroflow.fetch`), so Cancel can stop
one at once, wherever huggingface_hub is in it. Whatever a cancelled or failed download
wrote is removed: nothing is left half-written for the Engine to load.

Only the standard library is imported at load time: settings.py uses this module.
"""
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass, field

from zeroflow import frozen, storage
from zeroflow.paths import BASE_DIR

# The old files the migration moves (zeroflow.storage).
OLD_FILES = (".env", *storage.DATA_NAMES)


# ---------------------------------------------------------------- whose files are these
def _sid_text(psid) -> str | None:
    advapi32, kernel32 = ctypes.WinDLL("advapi32"), ctypes.WinDLL("kernel32")
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    text = wintypes.LPWSTR()
    if not advapi32.ConvertSidToStringSidW(psid, ctypes.byref(text)):
        return None
    value = text.value
    kernel32.LocalFree(ctypes.cast(text, ctypes.c_void_p))
    return value


def file_owner(path: str) -> str | None:
    """The owner of `path` as a SID ("S-1-5-21-…"); None when it cannot be read (a drive
    with no owners, such as FAT)."""
    try:
        advapi32, kernel32 = ctypes.WinDLL("advapi32"), ctypes.WinDLL("kernel32")
    except (AttributeError, OSError):
        return None
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    owner, descriptor = ctypes.c_void_p(), ctypes.c_void_p()
    if advapi32.GetNamedSecurityInfoW(ctypes.c_wchar_p(path), 1, 1, ctypes.byref(owner),
                                      None, None, None, ctypes.byref(descriptor)):
        return None
    try:
        return _sid_text(owner) if owner.value else None
    finally:
        kernel32.LocalFree(descriptor)


def current_user() -> str | None:
    """The SID of the Windows user running this process."""
    try:
        advapi32, kernel32 = ctypes.WinDLL("advapi32"), ctypes.WinDLL("kernel32")
    except (AttributeError, OSError):
        return None
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                          ctypes.POINTER(wintypes.HANDLE)]
    advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                             wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        return None
    try:
        size = wintypes.DWORD()
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))      # TokenUser
        buffer = ctypes.create_string_buffer(size.value)
        if not size.value or not advapi32.GetTokenInformation(token, 1, buffer, size,
                                                              ctypes.byref(size)):
            return None
        return _sid_text(ctypes.c_void_p.from_buffer(buffer).value)
    finally:
        kernel32.CloseHandle(token)


def old_files(old_dir: str) -> list[str]:
    return [os.path.join(old_dir, n) for n in OLD_FILES if os.path.exists(os.path.join(old_dir, n))]


def old_files_are_mine(old_dir: str, owner=None, me=None) -> bool:
    """True when the program folder holds old files and every one is this user's. A file
    whose owner cannot be read counts as this user's, as before 5c."""
    found = old_files(old_dir)
    if not found:
        return False
    owner, me = owner or file_owner, me or current_user
    user = me()
    return all(user is None or owner(path) in (None, user) for path in found)


def needs_setup(settings_path: str, old_dir: str, owner=None, me=None) -> bool:
    """The wizard runs only when there is no settings file and nothing of this user's
    to migrate."""
    if os.path.exists(settings_path):
        return False
    return not old_files_are_mine(old_dir, owner, me)


# ---------------------------------------------------------------- what this PC should run
@dataclass
class Recommendation:
    tier: str
    label: str
    values: dict
    reasons: list
    facts: dict


def _hardware():
    """check_hardware.py, at the top of the program folder (standard library only)."""
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
    import check_hardware
    return check_hardware


def recommendation(detect=None) -> Recommendation:
    """check_hardware's detect() and recommend(), unchanged: no logic of its own. Only the
    settings Zero- Flow has are kept, checked as the Engine checks them."""
    from zeroflow import settings
    hardware = _hardware()
    facts = (detect or hardware.detect)()
    tier, preset, reasons = hardware.recommend(facts)
    known = {name: value for name, value in preset.items() if name in settings.SPEC}
    checked, _ = settings.resolve(known)
    return Recommendation(tier, hardware.TIERS.get(tier, tier),
                          {name: checked[name] for name in known}, list(reasons), facts)


# ---------------------------------------------------------------- downloads
# Measured at the pinned revisions (zeroflow.models), so they do not change: Hub file
# metadata and the llama.cpp release's Content-Length, 2026-11-11.
SIZES = {
    "Systran/faster-whisper-large-v3": 3_090_835_702,
    "mobiuslabsgmbh/faster-whisper-large-v3-turbo": 1_621_665_983,
    "Systran/faster-whisper-medium": 1_530_571_735,
    "Systran/faster-whisper-small": 486_212_372,
    "Systran/faster-whisper-base": 147_882_941,
    "hexgrad/Kokoro-82M": 328_784_847,
    "google/gemma-4-E4B-it-qat-q4_0-gguf": 5_154_941_280,
    "google/gemma-4-E2B-it-qat-q4_0-gguf": 3_349_516_256,
    "runtime:cuda": 656_710_393,
    "runtime:vulkan": 32_183_022,
    "runtime:cpu": 19_553_417,
}
WHISPER_REPOS = {"large-v3": "Systran/faster-whisper-large-v3",
                 "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
                 "medium": "Systran/faster-whisper-medium", "small": "Systran/faster-whisper-small",
                 "base": "Systran/faster-whisper-base", "tiny": "Systran/faster-whisper-tiny"}
WHISPER_PATTERNS = ("config.json", "preprocessor_config.json", "model.bin", "tokenizer.json",
                    "vocabulary.*")
WHISPER_CHECK = ("config.json", "model.bin", "tokenizer.json")
READER_FILES = ("config.json", "kokoro-v1_0.pth", "voices/af_heart.pt", "voices/af_bella.pt",
                "voices/bf_emma.pt")


@dataclass(frozen=True)
class Item:
    kind: str                       # whisper, reader, ai, runtime
    name: str                       # the Hub repo, or the runtime's variant
    label: str
    size: int                       # bytes; 0 when not known
    patterns: tuple = field(default=())
    check: tuple = field(default=())


def downloads_for(values: dict, runtime: str, runtime_installed: bool) -> list[Item]:
    """What the choices need, in the order they are fetched."""
    items = []
    whisper = values.get("WHISPER_MODEL_NAME", "large-v3")
    repo = WHISPER_REPOS.get(whisper) or (whisper if "/" in whisper else None)
    if repo:
        items.append(Item("whisper", repo, f"Speech model ({whisper})", SIZES.get(repo, 0),
                          WHISPER_PATTERNS, WHISPER_CHECK))
    if values.get("READER_ON", True):
        items.append(Item("reader", "hexgrad/Kokoro-82M", "Reader voice",
                          SIZES["hexgrad/Kokoro-82M"], READER_FILES, READER_FILES))
    if values.get("AI_PROVIDER", "builtin") == "builtin":
        ai_repo = values.get("AI_BUILTIN_REPO", "google/gemma-4-E4B-it-qat-q4_0-gguf")
        ai_file = values.get("AI_BUILTIN_FILE", "gemma-4-E4B_q4_0-it.gguf")
        items.append(Item("ai", ai_repo, f"Built-in AI ({ai_file})", SIZES.get(ai_repo, 0),
                          (ai_file,), (ai_file,)))
        if not runtime_installed:
            items.append(Item("runtime", runtime, f"Built-in AI runtime ({runtime})",
                              SIZES.get(f"runtime:{runtime}", 0)))
    return items


def cached(item: Item, cache_dir: str) -> bool:
    """True when every file of `item` is already in the models folder."""
    if item.kind == "runtime":
        from zeroflow.llm import llama_runtime
        return llama_runtime.installed(item.name)
    from huggingface_hub import try_to_load_from_cache
    from zeroflow import models
    revision = models.revision(item.name)
    return all(isinstance(try_to_load_from_cache(item.name, name, cache_dir=cache_dir,
                                                 revision=revision), str)
               for name in item.check)


class Cancelled(Exception):
    pass


def _files_under(folder: str) -> set[str]:
    found = set()
    for root, dirs, files in os.walk(folder):
        found.update(os.path.join(root, d) + os.sep for d in dirs)
        found.update(os.path.join(root, f) for f in files)
    return found


def _remove_new(folder: str, before: set[str]) -> None:
    """Remove every file and folder under `folder` that was not there before."""
    new = sorted(_files_under(folder) - before, key=len, reverse=True)   # deepest first
    for path in new:
        try:
            if path.endswith(os.sep):
                os.rmdir(path)
            else:
                os.remove(path)
        except OSError:
            pass


def run_download(item: Item, cache_dir: str, fetch, progress, cancel: threading.Event) -> str:
    """Fetch one item: "done", "cancelled", or "failed: <why>". `fetch(item, cache_dir,
    on_bytes)` reports bytes as they arrive; each report checks for Cancel. A cancelled
    or failed download leaves nothing behind that was not there before."""
    os.makedirs(cache_dir, exist_ok=True)
    before = _files_under(cache_dir)
    done = 0

    def on_bytes(count: int) -> None:
        nonlocal done
        if cancel.is_set():
            raise Cancelled()
        done += count
        progress(done)

    try:
        fetch(item, cache_dir, on_bytes)
        if cancel.is_set():
            raise Cancelled()
        return "done"
    except Cancelled:
        _remove_new(cache_dir, before)
        return "cancelled"
    except Exception as e:
        _remove_new(cache_dir, before)
        return f"failed: {e}"


POLL_SECONDS = 0.25
CREATE_NO_WINDOW = 0x08000000


def _bytes_under(folder: str, before: set[str]) -> int:
    total = 0
    for path in _files_under(folder) - before:
        if not path.endswith(os.sep):
            try:
                total += os.path.getsize(path)
            except OSError:
                pass
    return total


def real_fetch(item: Item, cache_dir: str, on_bytes) -> None:
    """The real download. A model goes through huggingface_hub in a child process, its
    progress read from the size of what it has written; the runtime is installed by
    llm.llama_runtime, which checks its checksum and unpacks it in one step."""
    if item.kind == "runtime":
        from zeroflow.llm import llama_runtime
        llama_runtime.install(item.name, progress=on_bytes)
        return
    from zeroflow import models, signals
    request = {"repo": item.name, "revision": models.revision(item.name),
               "patterns": list(item.patterns), "cache_dir": cache_dir}
    env = dict(os.environ, HF_HOME=os.path.dirname(cache_dir), HF_HUB_CACHE=cache_dir,
               HF_XET_CHUNK_CACHE_SIZE_BYTES="0", HF_HUB_DISABLE_PROGRESS_BARS="1")
    before = _files_under(cache_dir)
    child = subprocess.Popen(frozen.child_command("fetch", json.dumps(request)),
                             cwd=BASE_DIR, env=env, stdout=subprocess.DEVNULL,
                             stderr=subprocess.PIPE, text=True, creationflags=CREATE_NO_WINDOW)
    signals.bind_child_to_this_process(child)
    errors = []
    reader = threading.Thread(target=lambda: errors.extend(child.stderr), daemon=True)
    reader.start()
    seen = 0
    try:
        while child.poll() is None:
            now = _bytes_under(cache_dir, before)
            on_bytes(max(0, now - seen))         # also where Cancel is noticed
            seen = max(seen, now)
            time.sleep(POLL_SECONDS)
        reader.join(timeout=2)
        if child.returncode != 0:
            last = next((line.strip() for line in reversed(errors) if line.strip()),
                        f"the download stopped (code {child.returncode})")
            raise OSError(last)
        on_bytes(max(0, _bytes_under(cache_dir, before) - seen))
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)


# ---------------------------------------------------------------- the tests
@dataclass
class Result:
    ok: bool
    message: str


MIC_SECONDS = 3
# Peak level a voice reaches and a muted or dead microphone does not (about -30 dBFS).
MIC_MIN_PEAK = 0.03


def mic_test(record, device: str, seconds: float = MIC_SECONDS) -> Result:
    """`record(device, seconds)` returns the samples (float, -1..1)."""
    try:
        import numpy as np
        samples = np.asarray(record(device, seconds), dtype="float32")
    except Exception as e:
        return Result(False, f"The microphone could not record: {e}")
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak < MIC_MIN_PEAK:
        return Result(False, "Nothing was heard. Check that this microphone is plugged in, "
                             "not muted, and allowed in Windows privacy settings.")
    return Result(True, "The microphone works.")


def real_record(device: str, seconds: float):
    import sounddevice as sd
    from zeroflow import microphone
    index, _ = microphone.resolve(device, sd.query_devices())
    clip = sd.rec(int(seconds * 16000), samplerate=16000, channels=1, dtype="float32",
                  device=index)
    sd.wait()
    return clip[:, 0]


AI_TEST_TEXT = "hello this is a test of zero flow"


def ai_test(ask) -> Result:
    """`ask(text)` returns the AI's answer, or None when it gave none."""
    try:
        answer = ask(AI_TEST_TEXT)
    except Exception as e:
        return Result(False, f"The AI did not answer: {e}")
    if not answer or not str(answer).strip():
        return Result(False, "The AI gave no answer. Polish and Translate will type your "
                             "own words until it does; Raw works without it.")
    return Result(True, "The AI answered.")


AI_TEST_TIMEOUT = 300           # the built-in AI's first load can take a while


def real_ask(values: dict, key: str | None, text: str) -> str | None:
    """Ask the chosen AI through the Engine's own code, in a child process that reads a
    temporary settings file holding the wizard's choices. The key never goes in that file:
    it is handed over on the child's standard input."""
    folder = tempfile.mkdtemp(prefix="zeroflow-aitest-")
    path = os.path.join(folder, storage.SETTINGS_NAME)
    try:
        storage.save(path, {n: v for n, v in values.items() if n != storage.KEY_NAME})
        env = dict(os.environ, ZEROFLOW_SETTINGS=path)
        from zeroflow import signals
        child = subprocess.Popen(frozen.child_command("ai-check"), cwd=BASE_DIR,
                                 env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, text=True,
                                 creationflags=CREATE_NO_WINDOW)
        signals.bind_child_to_this_process(child)
        try:
            out, _ = child.communicate((key or "") + "\n", timeout=AI_TEST_TIMEOUT)
        except subprocess.TimeoutExpired:
            child.kill()
            raise OSError(f"no answer within {AI_TEST_TIMEOUT} s")
        lines = [line for line in out.splitlines() if line.startswith("{")]
        if not lines:
            raise OSError(f"the test stopped (code {child.returncode})")
        answer = json.loads(lines[-1])
        if answer.get("why"):
            raise OSError(answer["why"])
        return answer.get("answer")
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
