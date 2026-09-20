"""
Zero- Flow Engine — hardware check.

Looks at this PC (graphics card and its memory, RAM, CPU), picks the matching preset
from presets/, and prints the settings to use and anything still missing. With
--apply it writes those settings into .env, keeping everything else you have set.

    python check_hardware.py                     # report + recommendation
    python check_hardware.py --apply             # ...and write the settings into .env
    python check_hardware.py --tier cpu-only     # use a tier of your choosing

Standard library only, so it runs straight after cloning, before `pip install`.
See docs/HARDWARE.md for what each tier means.
"""
import argparse
import ctypes
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRESETS_DIR = os.path.join(BASE_DIR, "presets")
ENV_FILE = os.path.join(BASE_DIR, ".env")
ENV_EXAMPLE = os.path.join(BASE_DIR, ".env.example")

TIERS = {
    "nvidia-desktop": "NVIDIA graphics card, 8 GB or more",
    "nvidia-laptop": "NVIDIA graphics, 4-7 GB",
    "cpu-only": "No dedicated graphics card",
    "amd-intel-gpu": "AMD Radeon / Intel Arc graphics card",
}
# Approximate first-run downloads, for the report.
WHISPER_DOWNLOAD = {"tiny": "75 MB", "base": "145 MB", "small": "480 MB",
                    "medium": "1.5 GB", "large-v3": "3 GB"}
DISPLAY_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"


# =====================================================================
# DETECTION
# =====================================================================
def classify_gpu(name):
    """(vendor, dedicated) for a display adapter name. Built-in graphics share system
    memory and cannot run the models any faster than the CPU, so they do not count."""
    n = name.lower()
    if "nvidia" in n:
        return "nvidia", True
    if "amd" in n or "radeon" in n:
        # "Radeon RX 7800 XT" / "Radeon Pro" are cards; plain "Radeon Graphics" / Vega
        # inside a Ryzen is built in.
        return "amd", bool(re.search(r"radeon\s*(rx|pro|vii)", n))
    if "intel" in n:
        # Discrete Arc cards carry a model number (A770, B580); "Arc Graphics" alone is
        # the built-in graphics of a Core Ultra.
        return "intel", bool(re.search(r"arc.*\b[ab]\d{3}\b", n))
    return "other", False


def _registry_gpus():
    """Display adapters and their memory from the registry — unlike WMI's AdapterRAM,
    which stops at 4 GB."""
    gpus = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, DISPLAY_CLASS) as cls:
            for i in range(64):
                try:
                    sub = winreg.EnumKey(cls, i)
                except OSError:
                    break
                if not sub.isdigit():
                    continue
                try:
                    with winreg.OpenKey(cls, sub) as key:
                        name = winreg.QueryValueEx(key, "DriverDesc")[0]
                        vram = 0
                        for value in ("HardwareInformation.qwMemorySize",
                                      "HardwareInformation.MemorySize"):
                            try:
                                raw = winreg.QueryValueEx(key, value)[0]
                                vram = int.from_bytes(raw, "little") if isinstance(raw, bytes) else int(raw)
                                break
                            except OSError:
                                pass
                        gpus.append({"name": name, "vram_gb": round(vram / 2**30, 1)})
                except OSError:
                    pass
    except ImportError:                          # not Windows
        pass
    return gpus


def _nvidia_smi_gpus():
    """NVIDIA cards and their exact memory, if the NVIDIA driver is installed."""
    if not shutil.which("nvidia-smi"):
        return []
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total",
                              "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    gpus = []
    for line in out.strip().splitlines():
        name, _, mib = line.rpartition(",")
        if name and mib.strip().isdigit():
            gpus.append({"name": name.strip(), "vram_gb": round(int(mib) / 1024, 1)})
    return gpus


def _ram_gb():
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    try:
        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return round(status.ullTotalPhys / 2**30, 1)
    except (AttributeError, OSError):
        return None


def _cpu_name():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    except (ImportError, OSError):
        return platform.processor() or "unknown CPU"


def detect():
    """Everything the recommendation depends on, as plain data."""
    gpus = _registry_gpus()
    exact = {g["name"]: g["vram_gb"] for g in _nvidia_smi_gpus()}
    for gpu in gpus:                             # prefer nvidia-smi's figure where it has one
        gpu["vram_gb"] = exact.get(gpu["name"], gpu["vram_gb"])
    for name, vram in exact.items():
        if not any(g["name"] == name for g in gpus):
            gpus.append({"name": name, "vram_gb": vram})
    for gpu in gpus:
        gpu["vendor"], gpu["dedicated"] = classify_gpu(gpu["name"])
    return {
        "windows": platform.system() == "Windows",
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "cpu": _cpu_name(),
        "threads": os.cpu_count() or 0,
        "ram_gb": _ram_gb(),
        "gpus": gpus,
    }


# =====================================================================
# RECOMMENDATION
# =====================================================================
def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_preset(tier):
    """The KEY="value" settings of presets/<tier>.env."""
    return parse_env(_read(os.path.join(PRESETS_DIR, f"{tier}.env")))


def parse_env(text):
    settings = {}
    for line in text.splitlines():
        match = re.match(r'\s*([A-Z0-9_]+)\s*=\s*("([^"]*)"|[^\s#]*)', line)
        if match:
            settings[match.group(1)] = match.group(3) if match.group(3) is not None else match.group(2)
    return settings


def recommend(facts, tier=None):
    """(tier, settings, reasons). Picks the tier from the best graphics card, then
    adjusts the preset for how much memory the card — or the PC — actually has."""
    reasons = []
    dedicated = [g for g in facts["gpus"] if g["dedicated"]]
    nvidia = max((g for g in dedicated if g["vendor"] == "nvidia"),
                 key=lambda g: g["vram_gb"], default=None)
    other = max((g for g in dedicated if g["vendor"] in ("amd", "intel")),
                key=lambda g: g["vram_gb"], default=None)
    ram = facts["ram_gb"] or 0

    if tier is None:
        if nvidia and nvidia["vram_gb"] >= 7.5:
            tier = "nvidia-desktop"
        elif nvidia and nvidia["vram_gb"] >= 3.5:
            tier = "nvidia-laptop"
        elif other:
            tier = "amd-intel-gpu"
        else:
            tier = "cpu-only"
            if nvidia:
                reasons.append(f"{nvidia['name']} has only {nvidia['vram_gb']} GB — too little "
                               f"for the models, so everything runs on the CPU.")
    settings = load_preset(tier)

    vram = nvidia["vram_gb"] if nvidia else 0
    if tier == "nvidia-desktop" and vram < 11:
        settings["WHISPER_COMPUTE_TYPE"] = "int8_float16"
        reasons.append(f"{vram} GB card: int8_float16 halves the speech model's memory "
                       f"(large-v3 3.9 GB -> 2.0 GB) to leave room for the AI model.")
    if tier == "nvidia-laptop" and vram < 5.5:
        settings["WHISPER_MODEL_NAME"] = "small"
        reasons.append(f"{vram} GB card: the 'small' speech model leaves room for the voice and AI.")
    if tier in ("cpu-only", "amd-intel-gpu") and ram and ram <= 9:
        settings["WHISPER_MODEL_NAME"] = "base"
        settings["OLLAMA_MODEL_NAME"] = "gemma2:2b"
        reasons.append(f"{ram} GB of RAM: the lightest speech and AI models keep Windows responsive.")
    if tier == "amd-intel-gpu" and other and other["vram_gb"] >= 7.5:
        reasons.append(f"{other['name']} ({other['vram_gb']} GB): if `ollama ps` shows '100% GPU' "
                       f"after a Polish, try OLLAMA_MODEL_NAME=\"qwen2.5:7b\".")
    return tier, settings, reasons


# =====================================================================
# SOFTWARE CHECKS
# =====================================================================
def engine_python():
    """The interpreter the launchers run the engine with — the same order as
    Launch_*.bat: venv, then python_env, then whatever `python` is."""
    for candidate in (os.path.join(BASE_DIR, "venv", "Scripts", "python.exe"),
                      os.path.join(BASE_DIR, "python_env", "python.exe")):
        if os.path.exists(candidate):
            return candidate
    return sys.executable


_VERSIONS_SCRIPT = """
import importlib.metadata as md, json, sys
out = {}
for name in sys.argv[1:]:
    try:
        out[name] = md.version(name)
    except md.PackageNotFoundError:
        out[name] = None
print(json.dumps(out))
"""


def installed_versions(packages):
    """{package: version or None} in the engine's interpreter. This script is usually
    run with the system Python while the packages live in venv/, so ask that one."""
    python = engine_python()
    if os.path.normcase(os.path.abspath(python)) == os.path.normcase(os.path.abspath(sys.executable)):
        found = {}
        for name in packages:
            try:
                found[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                found[name] = None
        return found
    try:
        out = subprocess.run([python, "-c", _VERSIONS_SCRIPT, *packages],
                             capture_output=True, text=True, timeout=60).stdout
        return json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError):
        return {name: None for name in packages}


def _ollama_models(env):
    url = env.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434/api/generate")
    try:
        with urllib.request.urlopen(url.replace("/api/generate", "/api/tags"), timeout=2) as r:
            return [m["name"] for m in json.load(r).get("models", [])]
    except Exception:
        return None


def _cached(repo):
    hub = os.environ.get("HF_HUB_CACHE") or os.path.join(
        os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface"), "hub")
    return os.path.isdir(os.path.join(hub, "models--" + repo.replace("/", "--")))


def software_checks(tier, settings):
    """[(ok, message)] for what is installed, running and downloaded."""
    notes = []
    versions = installed_versions(["faster-whisper", "kokoro", "torch", "nvidia-cublas-cu12"])
    where = os.path.relpath(engine_python(), BASE_DIR) if engine_python() != sys.executable else "this Python"
    torch = versions["torch"]
    uses_nvidia = tier.startswith("nvidia")
    if not versions["faster-whisper"] or not versions["kokoro"] or torch is None:
        notes.append((False, f"Python packages not installed yet ({where}) — see docs/INSTALL.md step 4"
                             + (" (CUDA build of torch first)" if uses_nvidia else "")))
    elif uses_nvidia and "+cu" not in torch:
        notes.append((False, f"torch {torch} is the CPU-only build, so the voice cannot use your "
                             f"card. Fix: pip install torch==2.5.1+cu121 --index-url "
                             f"https://download.pytorch.org/whl/cu121"))
    else:
        notes.append((True, f"packages installed ({where}); torch {torch}"
                            + (" (CUDA build)" if "+cu" in torch else "")))
    if uses_nvidia and torch is not None and versions["nvidia-cublas-cu12"] is None:
        notes.append((False, "nvidia-cublas-cu12 / nvidia-cudnn-cu12 are missing, so the speech "
                             "model cannot use your card: keep those two lines in requirements.txt"))

    env = parse_env(_read(ENV_FILE)) if os.path.exists(ENV_FILE) else {}
    models = _ollama_models(env)
    wanted = settings["OLLAMA_MODEL_NAME"]
    if models is None:
        notes.append((False, "Ollama is not running (or not installed) — start it from the Start menu."))
    elif not any(m == wanted or m == wanted + ":latest" for m in models):
        notes.append((False, f"Ollama does not have {wanted} yet: ollama pull {wanted}"))
    else:
        notes.append((True, f"Ollama is running and has {wanted}"))

    size = settings["WHISPER_MODEL_NAME"]
    repo = size if "/" in size else f"Systran/faster-whisper-{size}"
    if _cached(repo):
        notes.append((True, f"speech model {size} is downloaded"))
    else:
        notes.append((True, f"speech model {size} downloads on first start "
                            f"(about {WHISPER_DOWNLOAD.get(size, 'a few hundred MB')})"))
    if not _cached("hexgrad/Kokoro-82M"):
        notes.append((True, "the reading voice downloads on first start (about 330 MB)"))
    return notes


# =====================================================================
# .env
# =====================================================================
def merge_env(text, settings):
    """`text` (a .env file) with `settings` written in: existing lines keep their
    comments and position, missing keys are appended under one heading."""
    missing = dict(settings)
    out = []
    for line in text.splitlines():
        match = re.match(r'(\s*([A-Z0-9_]+)\s*=\s*)("[^"]*"|[^\s#]*)(.*)$', line)
        if match and match.group(2) in missing:
            line = f'{match.group(1)}"{missing.pop(match.group(2))}"{match.group(4)}'
        out.append(line)
    if missing:
        out += ["", "# --- Tuned for this PC by check_hardware.py ---"]
        out += [f'{key}="{value}"' for key, value in missing.items()]
    return "\n".join(out) + "\n"


def apply(settings):
    """Write `settings` into .env (created from .env.example if there is none yet).
    The previous .env is kept as .env.bak."""
    if os.path.exists(ENV_FILE):
        shutil.copyfile(ENV_FILE, ENV_FILE + ".bak")
        source = ENV_FILE
    else:
        source = ENV_EXAMPLE
    text = _read(source)
    with open(ENV_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(merge_env(text, settings))
    return source


# =====================================================================
# REPORT
# =====================================================================
def main(argv=None):
    parser = argparse.ArgumentParser(description="Recommend Zero- Flow settings for this PC.")
    parser.add_argument("--apply", action="store_true", help="write the settings into .env")
    parser.add_argument("--tier", choices=sorted(TIERS), help="use this tier instead of detecting one")
    args = parser.parse_args(argv)

    facts = detect()
    print("Zero- Flow hardware check")
    print("=" * 60)
    if not facts["windows"]:
        print("[!!] Zero- Flow runs on Windows 10/11 only (it hooks the Windows keyboard).")
    print(f"System : {facts['os']}, Python {facts['python']}")
    print(f"CPU    : {facts['cpu']} ({facts['threads']} threads)")
    print(f"RAM    : {facts['ram_gb']} GB")
    for gpu in facts["gpus"] or [{"name": "none found", "vram_gb": 0, "dedicated": False}]:
        kind = "graphics card" if gpu["dedicated"] else "built-in graphics, not used"
        print(f"GPU    : {gpu['name']} — {gpu['vram_gb']} GB ({kind})")

    tier, settings, reasons = recommend(facts, args.tier)
    print(f"\nYour tier: {tier} — {TIERS[tier]}"
          + (" (chosen with --tier)" if args.tier else ""))
    for reason in reasons:
        print(f"  - {reason}")
    print("\nRecommended settings (presets/%s.env):" % tier)
    for key, value in settings.items():
        print(f'  {key}="{value}"')

    print("\nChecks:")
    for ok, message in software_checks(tier, settings):
        print(f"  [{'ok' if ok else '!!'}] {message}")

    if args.apply:
        source = apply(settings)
        backup = " (previous .env saved as .env.bak)" if source == ENV_FILE else " (from .env.example)"
        print(f"\nWrote these settings into .env{backup}. Restart the engine to use them.")
    else:
        print("\nTo use them: python check_hardware.py --apply   (or edit .env by hand)")
    print("More: docs/HARDWARE.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
