"""The built-in AI's runtime: llama.cpp's llama-server, one build per kind of PC.

    cuda     NVIDIA graphics cards (CUDA 12.4 — runs on any recent NVIDIA driver)
    vulkan   AMD Radeon and Intel Arc cards
    cpu      everything else; slower answers

The build is pinned (BUILD) and every archive is checked against its published SHA-256
before anything is unpacked, so a changed or corrupted download is never run. The
runtime lives in runtime/llama/<variant>/ in the program folder (git-ignored);
tools/get_llama.py installs it.
"""
import hashlib
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile

from zeroflow.paths import BASE_DIR
from zeroflow.settings import LLAMA_VARIANT

BUILD = "b11619"
RELEASE_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{BUILD}/"
RUNTIME_DIR = os.path.join(BASE_DIR, "runtime", "llama")
# (archive, SHA-256) per variant, as published with the release.
ARCHIVES = {
    "cuda": [
        (f"llama-{BUILD}-bin-win-cuda-12.4-x64.zip",
         "827178aa8951771e7058d8d8a18c72a27acd2102a14f4b0764023e9d78a89693"),
        ("cudart-llama-bin-win-cuda-12.4-x64.zip",
         "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6"),
    ],
    "vulkan": [
        (f"llama-{BUILD}-bin-win-vulkan-x64.zip",
         "ef6ca0c1113332ffb903318c7958cd7cb3679f52be7a5dab4de2bd6106d78235"),
    ],
    "cpu": [
        (f"llama-{BUILD}-bin-win-cpu-x64.zip",
         "d8f0d474c891c62248ba030a1774200884582ef3661c3fa91a25818e303ca9bc"),
    ],
}
SERVER = "llama-server.exe"


class RuntimeInstallError(Exception):
    pass


def variant_dir(variant: str) -> str:
    return os.path.join(RUNTIME_DIR, variant)


def server_path(variant: str) -> str:
    return os.path.join(variant_dir(variant), SERVER)


def installed(variant: str) -> bool:
    return os.path.isfile(server_path(variant))


def pick_variant(gpu_names: list[str]) -> str:
    """The build for these display adapters — classified exactly as check_hardware.py
    does: an NVIDIA card wins, then a dedicated AMD or Intel card; built-in graphics
    run the model no faster than the CPU."""
    kinds = [_hardware().classify_gpu(name) for name in gpu_names]
    if any(vendor == "nvidia" for vendor, _ in kinds):
        return "cuda"
    if any(dedicated and vendor in ("amd", "intel") for vendor, dedicated in kinds):
        return "vulkan"
    return "cpu"


def chosen_variant() -> str:
    """LLAMA_VARIANT from .env, or — with "auto" — the one this PC's cards call for."""
    if LLAMA_VARIANT != "auto":
        return LLAMA_VARIANT
    return pick_variant([gpu["name"] for gpu in _hardware().detect()["gpus"]])


def _hardware():
    """check_hardware.py, at the top of the program folder (standard library only)."""
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
    import check_hardware
    return check_hardware


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(name: str, dest: str) -> None:
    print(f"  downloading {name} ...", flush=True)
    with urllib.request.urlopen(RELEASE_URL + name, timeout=60) as response, \
            open(dest, "wb") as out:
        total, done = int(response.headers.get("Content-Length") or 0), 0
        while block := response.read(1 << 20):
            out.write(block)
            done += len(block)
            if total:
                print(f"\r  {done / 2**20:6.0f} / {total / 2**20:.0f} MB", end="", flush=True)
    print()


def _unpack(archive: str, dest: str) -> None:
    """Unpack, refusing any entry that would land outside `dest`."""
    root = os.path.realpath(dest)
    with zipfile.ZipFile(archive) as z:
        for entry in z.namelist():
            target = os.path.realpath(os.path.join(dest, entry))
            if not (target == root or target.startswith(root + os.sep)):
                raise RuntimeInstallError(f"{os.path.basename(archive)} tries to write "
                                          f"outside its folder ({entry}); not installed.")
        z.extractall(dest)


def install(variant: str, from_dir: str | None = None) -> str:
    """Install `variant`'s runtime: each archive taken from `from_dir` when it is there
    (already downloaded), otherwise downloaded; verified; then unpacked. Nothing is
    left half-installed: the files go to a temporary folder first. Returns the folder."""
    if variant not in ARCHIVES:
        raise RuntimeInstallError(f"unknown build {variant!r}; choose one of {', '.join(ARCHIVES)}")
    work = tempfile.mkdtemp(prefix="zeroflow-llama-")
    try:
        staged = os.path.join(work, "unpacked")
        os.makedirs(staged)
        for name, expected in ARCHIVES[variant]:
            local = os.path.join(from_dir, name) if from_dir else None
            archive = local if local and os.path.isfile(local) else os.path.join(work, name)
            if archive != local:
                _download(name, archive)
            actual = _sha256(archive)
            if actual != expected:
                raise RuntimeInstallError(f"{name} does not match its published checksum "
                                          f"(got {actual[:12]}…, expected {expected[:12]}…); "
                                          f"not installed.")
            _unpack(archive, staged)
        if not os.path.isfile(os.path.join(staged, SERVER)):
            raise RuntimeInstallError(f"the {variant} build has no {SERVER}; not installed.")
        shutil.rmtree(variant_dir(variant), ignore_errors=True)
        os.makedirs(RUNTIME_DIR, exist_ok=True)
        shutil.move(staged, variant_dir(variant))
        return variant_dir(variant)
    finally:
        shutil.rmtree(work, ignore_errors=True)
