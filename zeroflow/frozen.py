"""Zero- Flow as a PyInstaller build, and the same code run from source.

In a build, sys.executable is ZeroFlow.exe, not Python, so `[sys.executable, "-m", ...]`
would start a second Engine. Every child process is started through child_command():
from source `python -m <module>`, in a build `ZeroFlow.exe --child <role>`, which
zero_flow.py hands to run_child() before anything else loads.

Only the standard library is imported here: zero_flow.py calls run_child() first.
"""
import os
import runpy
import sys

from zeroflow.paths import BASE_DIR

CHILD_FLAG = "--child"
# The roles a child process can have, and the module that plays each.
CHILD_MODULES = {"reader": "reader", "fetch": "zeroflow.fetch", "ai-check": "zeroflow.ai_check"}
ENTRY_POINT = "zero_flow.py"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _frozen(frozen):
    return is_frozen() if frozen is None else frozen


def child_command(role: str, *args: str, frozen=None, executable=None) -> list[str]:
    """The command that starts the child playing `role` (KeyError for an unknown one)."""
    module = CHILD_MODULES[role]
    executable = executable or sys.executable
    if _frozen(frozen):
        return [executable, CHILD_FLAG, role, *args]
    return [executable, "-m", module, *args]


def engine_command(*args: str, frozen=None, executable=None, base_dir=BASE_DIR) -> list[str]:
    """The command that starts a new Engine (a restart after Save)."""
    executable = executable or sys.executable
    if _frozen(frozen):
        return [executable, *args]
    return [executable, os.path.join(base_dir, ENTRY_POINT), *args]


CUDA_PACKAGES = ("cublas", "cudnn")


def cuda_dll_dirs(search_path, frozen=None, bundle_dir=None) -> list[str]:
    """The folders that hold the CUDA libraries Whisper (CTranslate2) needs.

    From source: the pip packages nvidia-cublas-cu12 / nvidia-cudnn-cu12, found on
    `search_path` (sys.path). In a build: torch's own lib folder in the bundle, which
    carries cuBLAS and cuDNN too; measured 2026-11-12 (tools/measure_cuda_from_torch.py),
    so the GPU edition does not ship the nvidia packages as well (1.9 GB). A CPU build
    has neither, and gets an empty list."""
    found = []
    for entry in search_path:
        for lib in CUDA_PACKAGES:
            folder = os.path.join(entry, "nvidia", lib, "bin")
            if os.path.isdir(folder):
                found.append(folder)
    if _frozen(frozen):
        bundle_dir = bundle_dir or getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        torch_lib = os.path.join(bundle_dir, "torch", "lib")
        if os.path.isdir(torch_lib):
            found.append(torch_lib)
    return found


def run_child(argv: list[str], run_module=runpy.run_module) -> bool:
    """Run the child `argv` asks for (`<exe> --child <role> ...`) and return True, or
    return False when it asks for none and the Engine should start. An unknown role
    exits with code 2. The module sees its own arguments in sys.argv."""
    if argv[1:2] != [CHILD_FLAG]:
        return False
    role = argv[2] if len(argv) > 2 else ""
    if role not in CHILD_MODULES:
        if sys.stderr is not None:
            sys.stderr.write(f"Unknown child role: {role!r}\n")
        raise SystemExit(2)
    sys.argv = [argv[0], *argv[3:]]
    reopen_std_streams()
    run_module(CHILD_MODULES[role], run_name="__main__", alter_sys=True)
    return True


_STREAMS = (("stdin", 0, "r"), ("stdout", 1, "w"), ("stderr", 2, "w"))


class _Sink:
    """Where output goes when Windows gave the process nowhere to write it."""
    def write(self, text):
        return len(text)

    def flush(self):
        pass

    def read(self, *args):
        return ""

    readline = read


def reopen_std_streams(target=sys, opener=os.fdopen) -> None:
    """A windowed build sets sys.stdin/stdout/stderr to None even when the parent passed
    pipes; the AI test reads its answer from the child's stdout. Each missing stream is
    reopened from its handle, or becomes a sink when there is none."""
    for name, fd, mode in _STREAMS:
        if getattr(target, name) is not None:
            continue
        try:
            stream = opener(fd, mode, encoding="utf-8", errors="replace", closefd=False)
        except (OSError, ValueError):
            stream = _Sink()
        setattr(target, name, stream)
