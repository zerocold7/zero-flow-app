"""Licence audit (Phase 7): every package a PyInstaller build ships, every native library
bundled inside them that changes the picture, and every model first run downloads.
Writes THIRD-PARTY-NOTICES.txt and prints a summary by licence class.

    venv\\Scripts\\python tools\\licence_audit.py [build\\gpu\\zeroflow] [--offline]

The shipped packages are read from the build's own lists (PYZ-00.toc, COLLECT-00.toc),
so a package that is installed but not shipped is not in the notices. Model licences
come from each model card on the Hugging Face Hub, at the revision zeroflow.models pins
(--offline skips them). Exit code 1 when anything is strong copyleft, proprietary or
unknown, so the build script can stop on it.
"""
import ast
import os
import re
import sys
from importlib import metadata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

NOTICES = os.path.join(ROOT, "THIRD-PARTY-NOTICES.txt")

PERMISSIVE, WEAK, REDIST, STRONG, PROPRIETARY, UNKNOWN = (
    "permissive", "weak copyleft", "proprietary, redistributable", "strong copyleft",
    "proprietary", "unknown")

# Checked in this order: the first match wins, so the copyleft words come first.
_TEXT_RULES = (
    (r"\bAGPL|Affero", STRONG),
    (r"\bLGPL|Lesser General Public|Library General Public", WEAK),
    (r"\bGPL|General Public License", STRONG),
    (r"\bMPL|Mozilla Public", WEAK),
    (r"\bEPL|Eclipse Public", WEAK),
    (r"NVIDIA|Proprietary|LicenseRef", PROPRIETARY),
    (r"\bMIT\b|Apache|\bBSD|\bISC\b|\bPSF|Python Software Foundation|Unlicense|"
     r"\bZlib\b|zlib/libpng|\bHPND\b|CC0|BSL-1\.0|Boost|Public Domain|\bCNRI\b|0BSD",
     PERMISSIVE),
)
# An "A OR B" licence lets us pick the lightest of them.
_ORDER = (PERMISSIVE, WEAK, REDIST, STRONG, PROPRIETARY, UNKNOWN)


def classify(expression: str) -> str:
    """The licence class of a licence name, SPDX expression or licence text."""
    if not expression or not expression.strip():
        return UNKNOWN
    choices = re.split(r"\s+OR\s+", expression) if " OR " in expression else [expression]
    classes = []
    for choice in choices:
        found = UNKNOWN
        for pattern, cls in _TEXT_RULES:
            if re.search(pattern, choice):
                found = cls
                break
        classes.append(found)
    return min(classes, key=_ORDER.index)


# Packages whose metadata is missing or misleading for what the build ships. Each says
# where the answer was checked.
OVERRIDES = {
    # No licence in its metadata or wheel; github.com/thewh1teagle/espeakng-loader is MIT
    # (checked 2026-11-12). The espeak-ng library it carries is listed under NATIVE.
    "espeakng-loader": "MIT",
    # Only the bootloader ships, and its exception allows any licence for the program.
    "pyinstaller": "GPL-2.0-or-later WITH Bootloader-exception (bootloader only: MIT-like)",
}
# Classes the override settles, when its text alone would read as copyleft.
OVERRIDE_CLASS = {"pyinstaller": PERMISSIVE}


def licence_class(name: str, licence: str) -> str:
    return OVERRIDE_CLASS.get(name.lower()) or classify(licence)


def licence_of(dist) -> str:
    """Best licence name for an installed distribution: an override, the SPDX expression,
    else the trove classifiers, else a short License field, else the start of its
    licence file."""
    meta = dist.metadata
    if meta["Name"].lower().replace("_", "-") in OVERRIDES:
        return OVERRIDES[meta["Name"].lower().replace("_", "-")]
    expression = meta.get("License-Expression")
    if expression:
        return expression.strip()
    trove = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or []
             if c.startswith("License ::") and "OSI Approved" != c.split("::")[-1].strip()]
    if trove:
        return " OR ".join(trove)
    field = (meta.get("License") or "").strip()
    if field and len(field) < 80 and "\n" not in field:
        return field
    for text in licence_texts(dist):
        head = " ".join(text.split()[:40])
        if classify(head) != UNKNOWN:
            return head[:80]
    return field.splitlines()[0][:80] if field else ""


_LICENCE_FILE = re.compile(r"(^|/)(LICEN[CS]E|COPYING|NOTICE|AUTHORS)[^/]*$", re.I)


def licence_texts(dist) -> list[str]:
    texts = []
    for f in dist.files or ():
        name = str(f).replace("\\", "/")
        if ".dist-info/" in name and _LICENCE_FILE.search(name):
            try:
                texts.append(dist.locate_file(f).read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
    return texts


# ---------------------------------------------------------------- what the build ships
def _toc(path: str):
    with open(path, encoding="utf-8") as f:
        return ast.literal_eval(f.read())


def shipped_sources(workpath: str) -> set[str]:
    """Every source file the build took (modules, binaries, data), normalised."""
    sources = set()
    _, modules = _toc(os.path.join(workpath, "PYZ-00.toc"))
    for _, src, _ in modules:
        sources.add(os.path.normcase(os.path.abspath(src)))
    collect = _toc(os.path.join(workpath, "COLLECT-00.toc"))
    for entry in collect[0]:
        if len(entry) == 3 and entry[1]:
            sources.add(os.path.normcase(os.path.abspath(entry[1])))
    return sources


def shipped_distributions(sources: set[str]):
    """The installed distributions that own at least one shipped file."""
    found = {}
    for dist in metadata.distributions():
        for f in dist.files or ():
            if os.path.normcase(os.path.abspath(dist.locate_file(f))) in sources:
                found[dist.metadata["Name"].lower()] = dist
                break
    return sorted(found.values(), key=lambda d: d.metadata["Name"].lower())


# ---------------------------------------------------------------- native libraries
# Libraries bundled inside a wheel whose licence is stronger than the wheel's own.
# Matched on the start of the file name in the build folder.
NATIVE = {
    "libx264": ("x264, inside PyAV's FFmpeg", "GPL-2.0-or-later"),
    "libx265": ("x265, inside PyAV's FFmpeg", "GPL-2.0-or-later"),
    "postproc": ("FFmpeg libpostproc, inside PyAV", "GPL-2.0-or-later"),
    "avcodec": ("FFmpeg, inside PyAV (built with GPL parts)", "LGPL-2.1-or-later"),
    "espeak-ng": ("espeak-ng, inside espeakng-loader", "GPL-3.0-or-later"),
    "libgmp": ("GMP, inside PyAV", "LGPL-3.0-or-later OR GPL-2.0-or-later"),
    # Redistributable under their vendors' terms, which must be named in the notices.
    "cublas": ("NVIDIA cuBLAS", "LicenseRef-NVIDIA-CUDA-EULA (redistributable)"),
    "cudnn": ("NVIDIA cuDNN", "LicenseRef-NVIDIA-cuDNN-SLA (redistributable)"),
    "cudart": ("NVIDIA CUDA runtime", "LicenseRef-NVIDIA-CUDA-EULA (redistributable)"),
    "cufft": ("NVIDIA cuFFT", "LicenseRef-NVIDIA-CUDA-EULA (redistributable)"),
    "curand": ("NVIDIA cuRAND", "LicenseRef-NVIDIA-CUDA-EULA (redistributable)"),
    "cusolver": ("NVIDIA cuSOLVER", "LicenseRef-NVIDIA-CUDA-EULA (redistributable)"),
    "cusparse": ("NVIDIA cuSPARSE", "LicenseRef-NVIDIA-CUDA-EULA (redistributable)"),
    "nvrtc": ("NVIDIA NVRTC", "LicenseRef-NVIDIA-CUDA-EULA (redistributable)"),
    "nvjitlink": ("NVIDIA nvJitLink", "LicenseRef-NVIDIA-CUDA-EULA (redistributable)"),
    "msvcp140": ("Microsoft Visual C++ runtime", "LicenseRef-Microsoft-VC-Redist"),
    "vcruntime140": ("Microsoft Visual C++ runtime", "LicenseRef-Microsoft-VC-Redist"),
}
# Proprietary, but the vendor allows shipping these files with an application.
REDISTRIBUTABLE = ("NVIDIA", "Microsoft")


def native_libraries(dist_dir: str) -> list[tuple[str, str, str]]:
    seen = {}
    for root, _, files in os.walk(dist_dir):
        for name in files:
            for prefix, (label, licence) in NATIVE.items():
                if name.lower().startswith(prefix) and name.lower().endswith(".dll"):
                    seen[prefix] = (label, licence, os.path.relpath(os.path.join(root, name),
                                                                    dist_dir))
    return [seen[k] for k in sorted(seen)]


# ---------------------------------------------------------------- models
def model_licences(offline: bool) -> list[tuple[str, str, str]]:
    from zeroflow import first_run, models
    repos = sorted({*first_run.WHISPER_REPOS.values(),
                    *(r for r in first_run.SIZES if "/" in r)})
    rows = []
    for repo in repos:
        licence = "(not checked: --offline)"
        if not offline:
            try:
                from huggingface_hub import model_info
                card = model_info(repo, revision=models.revision(repo)).card_data
                licence = (card or {}).get("license") or ""
                if licence == "other":
                    licence = "other: " + ((card or {}).get("license_name") or "see model card")
            except Exception as e:
                licence = f"(lookup failed: {e.__class__.__name__})"
        rows.append((repo, models.revision(repo) or "", licence))
    return rows


# The built-in AI runtime is downloaded at first run from the llama.cpp releases.
DOWNLOADED_PROGRAMS = (("llama.cpp (llama-server)", "MIT",
                        "https://github.com/ggml-org/llama.cpp"),
                       ("NVIDIA CUDA runtime in the llama.cpp CUDA build",
                        "LicenseRef-NVIDIA-CUDA-EULA (redistributable files)",
                        "https://docs.nvidia.com/cuda/eula/"))


# ---------------------------------------------------------------- GPL source offer
# GPL-3 section 6: whoever receives the program can get the complete source of its GPL
# parts. ADR 0003. Zero- Flow's own source is published with each release (Phase 8).
GPL_TEXT = os.path.join(ROOT, "packaging", "licenses", "GPL-3.0.txt")
GPL_SOURCES = (
    ("espeak-ng {espeak}", "https://github.com/espeak-ng/espeak-ng/releases/tag/{espeak}"),
    ("phonemizer-fork 3.3.2", "https://pypi.org/project/phonemizer-fork/3.3.2/#files"),
    ("espeakng-loader 0.2.4 (MIT; builds the espeak-ng library above)",
     "https://github.com/thewh1teagle/espeakng-loader"),
)
ZEROFLOW_SOURCE = "https://github.com/zerocold7/zero-flow-app (public from the 2.0.0 release)"


def espeak_version(dist_dir: str) -> str:
    """The espeak-ng version in the build, read from the library itself."""
    import ctypes
    path = os.path.join(dist_dir, "_internal", "espeakng_loader", "espeak-ng.dll")
    try:
        library = ctypes.WinDLL(path)
        library.espeak_Info.restype = ctypes.c_char_p
        library.espeak_Info.argtypes = [ctypes.c_void_p]
        return library.espeak_Info(None).decode()
    except (OSError, AttributeError):
        return "unknown"


def short_name(label: str) -> str:
    """"x264, inside PyAV's FFmpeg" -> "x264"; the name build_installer accepts by."""
    return label.split(",")[0].split(" (")[0]


# ---------------------------------------------------------------- report
def audit(workpath: str, offline: bool = False) -> dict:
    """Classify everything the build at `workpath` ships and write THIRD-PARTY-NOTICES.txt.
    Returns {licence class: [names]} (package names, short names of native libraries)."""
    edition = os.path.basename(os.path.dirname(workpath))
    dist_dir = os.path.join(ROOT, "dist", edition, "ZeroFlow")
    dists = shipped_distributions(shipped_sources(workpath))
    rows = [(d.metadata["Name"], d.version, licence_of(d), d) for d in dists]
    natives = native_libraries(dist_dir)
    model_rows = model_licences(offline)

    by_class, names = {}, {}
    for name, version, lic, _ in rows:
        cls = licence_class(name, lic)
        by_class.setdefault(cls, []).append(f"{name} {version} ({lic or '?'})")
        names.setdefault(cls, []).append(name.lower().replace("_", "-"))
    for label, lic, _ in natives:
        cls = REDIST if label.startswith(REDISTRIBUTABLE) else classify(lic)
        by_class.setdefault(cls, []).append(f"{label} ({lic})")
        names.setdefault(cls, []).append(short_name(label))
    print(f"Build: {workpath}\nShipped packages: {len(rows)}, flagged native libraries: "
          f"{len(natives)}, models: {len(model_rows)}\n")
    for cls in _ORDER:
        items = by_class.get(cls, [])
        print(f"{cls}: {len(items)}")
        if cls != PERMISSIVE:
            for item in items:
                print(f"    {item}")
    print("\nModels (downloaded at first run, not shipped):")
    for repo, _, lic in model_rows:
        print(f"    {repo}: {lic}")

    espeak = espeak_version(dist_dir)
    with open(NOTICES, "w", encoding="utf-8", newline="\r\n") as out:
        out.write("Zero- Flow - third-party notices\n\n"
                  "Zero- Flow ships the components below. Each keeps its own licence; "
                  "the full texts follow the list.\n"
                  "Because it includes GPL-3 components (espeak-ng, phonemizer-fork), the "
                  "program as a whole is distributed under the GNU General Public License "
                  "version 3; its full text is at the end of this file.\n"
                  f"Generated by tools/licence_audit.py from the {edition} build.\n\n")
        out.write("=== Source code ===\n\n")
        out.write(f"Zero- Flow: {ZEROFLOW_SOURCE}\n")
        for label, url in GPL_SOURCES:
            out.write(f"{label.format(espeak=espeak)}: {url.format(espeak=espeak)}\n")
        out.write("\n=== Python packages shipped with the program ===\n\n")
        for name, version, lic, _ in rows:
            out.write(f"{name} {version} - {lic or 'licence not stated'}\n")
        out.write("\n=== Native libraries inside those packages ===\n\n")
        for label, lic, path in natives:
            out.write(f"{label} - {lic} - {path}\n")
        out.write("\n=== Downloaded at first run (not part of the installer) ===\n\n")
        for repo, rev, lic in model_rows:
            out.write(f"https://huggingface.co/{repo} (revision {rev[:12]}) - {lic}\n")
        for name, lic, url in DOWNLOADED_PROGRAMS:
            out.write(f"{name} - {lic} - {url}\n")
        out.write("\n=== Licence texts ===\n")
        for name, version, lic, dist in rows:
            texts = licence_texts(dist)
            out.write(f"\n----- {name} {version} ({lic or 'licence not stated'}) -----\n\n")
            out.write("\n\n".join(t.strip() for t in texts) + "\n" if texts
                      else "(no licence file in the package; see its project page)\n")
        with open(GPL_TEXT, encoding="utf-8") as gpl:
            out.write(f"\n----- GNU General Public License version 3 (espeak-ng {espeak}, "
                      "and the program as a whole) -----\n\n" + gpl.read().strip() + "\n")
    print(f"\nWrote {NOTICES} ({os.path.getsize(NOTICES) // 1024} KB), espeak-ng {espeak}")
    return names


def main(argv):
    offline = "--offline" in argv
    args = [a for a in argv if not a.startswith("--")]
    workpath = os.path.abspath(args[0] if args else os.path.join(ROOT, "build", "gpu", "zeroflow"))
    names = audit(workpath, offline)
    flagged = sum(len(names.get(c, [])) for c in (STRONG, PROPRIETARY, UNKNOWN))
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
