# PyInstaller one-folder build of Zero- Flow (Phase 7).
#
#   venv\Scripts\pyinstaller packaging\zeroflow.spec --noconfirm --distpath dist\gpu --workpath build\gpu
#
# The edition is the venv it runs in: the GPU edition from venv\ (CUDA torch), CPU-light
# from venv-cpu\ (CPU-only torch). tools/build_installer.py runs it for both, then
# tools/check_build.py checks the result. Children run as `ZeroFlow.exe --child <role>`
# (zeroflow/frozen.py), so their modules are listed as hidden imports.
import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [(os.path.join(ROOT, "presets"), "presets"),
         (os.path.join(ROOT, "logo_tray.ico"), "."),
         (os.path.join(ROOT, "logo.jpg"), ".")]
binaries = []
hidden = ["reader", "reader.__main__", "zeroflow.fetch", "zeroflow.ai_check", "check_hardware"]
# Packages that load data files or modules by name at run time.
for package in ("misaki", "kokoro", "espeakng_loader", "en_core_web_sm", "language_tags",
                "spacy", "thinc", "faster_whisper"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hidden += h

# Never shipped: development tools, the optional Claude package, and what a developer's
# venv may hold from before 2.0 (pystray, reportlab and the pillow they pull in), which
# some libraries import only if present.
# tests/test_packaging.py checks the GPU build ships nothing requirements.txt does not pull in.
LEFTOVERS = ["pytest", "_pytest", "py", "pluggy", "iniconfig", "pytestqt", "ruff", "anthropic",
             "PIL", "pystray", "reportlab", "soundfile", "_soundfile", "_soundfile_data",
             "sniffio"]
# tomli installed as its own package is pip-audit's (a dev tool). Where it is not, a
# PyInstaller hook maps it onto setuptools' own copy, and excluding it breaks that hook.
import importlib.util
if importlib.util.find_spec("tomli") is not None:
    LEFTOVERS.append("tomli")
EXCLUDES = LEFTOVERS + ["tkinter", "IPython", "matplotlib", "tensorboard"]
# Their metadata folders too, which some hooks copy (pillow-13.0.0.dist-info ...).
LEFTOVER_METADATA = ("pytest-", "pluggy-", "iniconfig-", "pillow-", "soundfile-", "sniffio-", "tomli-",
                     "anthropic-", "pystray-", "reportlab-")

a = Analysis([os.path.join(ROOT, "zero_flow.py")], pathex=[ROOT], binaries=binaries,
             datas=datas, hiddenimports=hidden, excludes=EXCLUDES, noarchive=False,
             # LGPL: num2words ships as loose .py files the user can replace.
             module_collection_mode={"num2words": "py"})


# PyAV out, its stand-in in (packaging/stubs/av.py): only faster_whisper/audio.py imports
# it, to decode audio files, and its FFmpeg is a GPL build.
def is_av(entry) -> bool:
    name, source = entry[0].replace("\\", "/"), (entry[1] or "").replace("\\", "/")
    return (name == "av" or name.startswith(("av.", "av/", "av.libs/", "av-"))
            or "/site-packages/av/" in source or "/site-packages/av.libs/" in source)


a.pure = [x for x in a.pure if not is_av(x)] + [
    ("av", os.path.join(ROOT, "packaging", "stubs", "av.py"), "PYMODULE")]
a.binaries = [x for x in a.binaries if not is_av(x)]
a.datas = [x for x in a.datas if not is_av(x)
           and not x[0].replace("\\", "/").lower().startswith(LEFTOVER_METADATA)]

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ZeroFlow", console=False,
          icon=os.path.join(ROOT, "logo_tray.ico"), upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="ZeroFlow", upx=False)
