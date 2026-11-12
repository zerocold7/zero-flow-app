"""Check a finished one-folder build (Phase 7): what it must hold and what it must not.

    venv\\Scripts\\python tools\\check_build.py gpu|cpu [dist\\<edition>\\ZeroFlow]

Exit code 1 and one line per problem when the build is wrong. tools/build_installer.py
runs it before the installer is made; tests/test_packaging.py checks the rules.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Every build needs these (paths relative to the build folder, "/" separators).
REQUIRED = (
    "ZeroFlow.exe",
    "LICENSE.txt",
    "THIRD-PARTY-NOTICES.txt",
    "_internal/logo_tray.ico",
    "_internal/presets/nvidia-desktop.env",
    "_internal/espeakng_loader/espeak-ng.dll",
    "_internal/en_core_web_sm/meta.json",
    # LGPL: shipped as loose source files, so it can be replaced (not packed in the exe).
    "_internal/num2words/__init__.py",
)
# A folder that must hold at least one file.
REQUIRED_FOLDERS = ("_internal/espeakng_loader/espeak-ng-data/",)

# Never shipped. GPL FFmpeg parts (PyAV is replaced by a stand-in: Zero- Flow never
# decodes audio files), development tools, the optional Claude package, and the nvidia
# packages (torch already carries the CUDA libraries Whisper uses).
FORBIDDEN_FOLDERS = ("_internal/av/", "_internal/av.libs/", "_internal/av-", "_internal/pytest/",
                     "_internal/pytestqt/", "_internal/anthropic/", "_internal/nvidia/",
                     "_internal/pil/", "_internal/pystray/", "_internal/reportlab/")
FORBIDDEN_NAMES = ("libx264", "libx265", "postproc-", "ruff.exe")

GPU_REQUIRED = ("_internal/torch/lib/torch_cuda.dll", "_internal/torch/lib/cublas64_12.dll")
CUDA_NAMES = ("torch_cuda", "cublas", "cudnn", "cufft", "curand", "cusolver", "cusparse",
              "cudart", "nvrtc", "nvjitlink", "c10_cuda")


def files_in(folder: str) -> list[str]:
    found = []
    for root, _, files in os.walk(folder):
        for name in files:
            found.append(os.path.relpath(os.path.join(root, name), folder).replace("\\", "/"))
    return found


def problems(files, edition: str) -> list[str]:
    """What is wrong with a build holding `files` (relative paths), for "gpu" or "cpu"."""
    if edition not in ("gpu", "cpu"):
        return [f"unknown edition {edition!r}"]
    have = {f.replace("\\", "/") for f in files}
    lower = {f.lower() for f in have}
    found = []
    for path in REQUIRED + (GPU_REQUIRED if edition == "gpu" else ()):
        if path.lower() not in lower:
            found.append(f"missing: {path}")
    for folder in REQUIRED_FOLDERS:
        if not any(f.startswith(folder.lower()) for f in lower):
            found.append(f"missing: {folder}")
    for path in sorted(lower):
        base = path.rsplit("/", 1)[-1]
        if any(path.startswith(folder) for folder in FORBIDDEN_FOLDERS):
            found.append(f"must not ship: {path}")
        elif base.startswith(FORBIDDEN_NAMES):
            found.append(f"must not ship: {path}")
        elif edition == "cpu" and base.endswith(".dll") and base.startswith(CUDA_NAMES):
            found.append(f"CUDA in the CPU edition: {path}")
    return found


def main(argv) -> int:
    edition = argv[0] if argv else "gpu"
    folder = argv[1] if len(argv) > 1 else os.path.join(ROOT, "dist", edition, "ZeroFlow")
    found = problems(files_in(folder), edition)
    for line in found:
        print(line)
    print(f"{edition} build {folder}: {'OK' if not found else f'{len(found)} problem(s)'}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
