"""Phase 7: the build and the installer.

- the version: one source (zeroflow.__version__), shown in the tray and the Settings
  window, and handed to the installer;
- tools/check_build.py: what a finished one-folder build must and must not hold
  (no GPL FFmpeg, num2words as loose files, CUDA only in the GPU edition ...);
- packaging/zeroflow.iss: per-user install, both editions under one AppId, the running
  Engine detected, the uninstaller asking before it deletes data.
The real build is checked here too when dist/ holds one; otherwise those tests skip.
"""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import zeroflow
from zeroflow import settings, signals

ISS = os.path.join(ROOT, "packaging", "zeroflow.iss")


# ---------------------------------------------------------------- the version
def test_the_version_is_one_semver_string():
    assert re.fullmatch(r"\d+\.\d+\.\d+(-(alpha|beta|rc)\.\d+)?", zeroflow.__version__)


def test_the_tray_tooltip_names_the_version():
    from zeroflow import app
    assert app.tray_tooltip("Active") == f"Zero- Flow {zeroflow.__version__} - Active"


def test_the_settings_window_shows_the_version(qtbot, tmp_path):
    from PySide6.QtWidgets import QLabel
    from zeroflow import credentials, i18n, storage
    from zeroflow.settings_window import SettingsWindow
    i18n.choose("en")
    values, _ = settings.resolve({})
    path = tmp_path / "settings.json"
    storage.save(str(path), {k: v for k, v in values.items() if k != "AI_API_KEY"})

    class Startup:
        def get(self):
            return False

        def set(self, on):
            pass
    win = SettingsWindow(values, str(path), credentials.MemoryStore(), [], Startup(),
                         lambda name, on: None, [])
    qtbot.addWidget(win)
    label = win.findChild(QLabel, "version")
    assert label is not None and zeroflow.__version__ in label.text()


def test_check_for_updates_is_in_the_window_and_off(qtbot, tmp_path):
    from PySide6.QtWidgets import QCheckBox
    from zeroflow import credentials, i18n, storage
    from zeroflow.settings_window import SettingsWindow
    i18n.choose("en")
    values, _ = settings.resolve({})
    path = tmp_path / "settings.json"
    storage.save(str(path), {k: v for k, v in values.items() if k != "AI_API_KEY"})

    class Startup:
        def get(self):
            return False

        def set(self, on):
            pass
    win = SettingsWindow(values, str(path), credentials.MemoryStore(), [], Startup(),
                         lambda name, on: None, [])
    qtbot.addWidget(win)
    box = win.findChild(QCheckBox, "CHECK_FOR_UPDATES")
    assert box is not None and box.isChecked() is False


def test_the_settings_table_lists_the_new_setting():
    with open(os.path.join(ROOT, "docs", "settings-table.md"), encoding="utf-8") as f:
        assert "CHECK_FOR_UPDATES" in f.read()


# ---------------------------------------------------------------- tools/check_build.py
GOOD_GPU = [
    "ZeroFlow.exe", "LICENSE.txt", "THIRD-PARTY-NOTICES.txt",
    "_internal/logo_tray.ico", "_internal/presets/nvidia-desktop.env",
    "_internal/espeakng_loader/espeak-ng.dll",
    "_internal/espeakng_loader/espeak-ng-data/phontab",
    "_internal/en_core_web_sm/meta.json", "_internal/num2words/__init__.py",
    "_internal/torch/lib/torch_cuda.dll", "_internal/torch/lib/cublas64_12.dll",
    "_internal/ctranslate2/ctranslate2.dll",
]
GOOD_CPU = [f for f in GOOD_GPU if "torch_cuda" not in f and "cublas" not in f]


def check():
    import check_build
    return check_build


def test_a_good_gpu_build_passes():
    assert check().problems(GOOD_GPU, "gpu") == []


def test_a_good_cpu_build_passes():
    assert check().problems(GOOD_CPU, "cpu") == []


@pytest.mark.parametrize("extra", [
    "_internal/av.libs/libx264-164-b33ed15d.dll", "_internal/av.libs/libx265-668b.dll",
    "_internal/av.libs/postproc-57-788c.dll", "_internal/av/__init__.pyc",
    # The same libraries brought in by some other package, outside av.libs.
    "_internal/libx264-164.dll", "_internal/cv2/libx265.dll",
])
def test_gpl_ffmpeg_fails_the_build(extra):
    assert check().problems(GOOD_GPU + [extra], "gpu")


@pytest.mark.parametrize("extra", ["_internal/pytest/__init__.py", "_internal/ruff.exe",
                                   "_internal/anthropic/__init__.py",
                                   "_internal/PIL/_imaging.cp312-win_amd64.pyd"])
def test_development_tools_fail_the_build(extra):
    assert check().problems(GOOD_GPU + [extra], "gpu")


@pytest.mark.parametrize("missing", ["_internal/espeakng_loader/espeak-ng.dll",
                                     "_internal/en_core_web_sm/meta.json",
                                     "THIRD-PARTY-NOTICES.txt", "LICENSE.txt",
                                     "_internal/presets/nvidia-desktop.env"])
def test_a_missing_part_fails_the_build(missing):
    assert check().problems([f for f in GOOD_GPU if f != missing], "gpu")


def test_num2words_packed_into_the_exe_fails_the_build():
    """LGPL: it ships as loose files the user can replace."""
    assert check().problems([f for f in GOOD_GPU if "num2words" not in f], "gpu")


def test_cuda_in_the_cpu_edition_fails_the_build():
    assert check().problems(GOOD_CPU + ["_internal/torch/lib/torch_cuda.dll"], "cpu")


def test_the_gpu_edition_without_cuda_fails_the_build():
    assert check().problems(GOOD_CPU, "gpu")


def test_the_nvidia_packages_are_not_shipped_twice():
    """torch already carries cuBLAS/cuDNN, and Whisper uses those (tests/test_frozen.py)."""
    assert check().problems(GOOD_GPU + ["_internal/nvidia/cudnn/bin/cudnn64_9.dll"], "gpu")


def test_the_gpu_build_ships_only_what_requirements_pull_in():
    """A developer's venv holds more than the program needs (pytest, soundfile, the
    pillow of pystray/reportlab); libraries that import those only if present dragged
    them into the first builds. The GPU build is made from venv\\, so its packages are
    compared with what requirements.txt pulls in there, plus PyInstaller's bootloader."""
    workpath = os.path.join(ROOT, "build", "gpu", "zeroflow")
    if not os.path.exists(os.path.join(workpath, "PYZ-00.toc")):
        pytest.skip("no gpu build in build/")
    import licence_audit
    from packaging.utils import canonicalize_name
    from tests.test_requirements import pulled_in, requirement_lines
    shipped = {canonicalize_name(d.metadata["Name"]) for d in
               licence_audit.shipped_distributions(licence_audit.shipped_sources(workpath))}
    allowed = pulled_in(requirement_lines()) | {"pyinstaller"}
    assert shipped - allowed == set()


@pytest.mark.parametrize("edition", ["gpu", "cpu"])
def test_the_real_build_passes_when_there_is_one(edition):
    folder = os.path.join(ROOT, "dist", edition, "ZeroFlow")
    if not os.path.isdir(os.path.join(folder, "_internal")):
        pytest.skip(f"no {edition} build in dist/")
    assert check().problems(check().files_in(folder), edition) == []


# ---------------------------------------------------------------- the PyAV stand-in
def load_av_stand_in():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "av_stand_in", os.path.join(ROOT, "packaging", "stubs", "av.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_av_stand_in_survives_being_inspected():
    """PySide6 runs inspect on every module imported after it; the first build died on
    the stand-in's answer to `__wrapped__`."""
    import inspect
    av = load_av_stand_in()
    assert inspect.unwrap(av) is av
    assert hasattr(av, "open") is False


def test_using_the_av_stand_in_says_why():
    av = load_av_stand_in()
    with pytest.raises(AttributeError, match="does not decode audio files"):
        av.open("clip.wav")


def test_faster_whisper_imports_with_the_stand_in(monkeypatch):
    import importlib
    monkeypatch.setitem(sys.modules, "av", load_av_stand_in())
    for name in [m for m in sys.modules if m.startswith("faster_whisper")]:
        monkeypatch.delitem(sys.modules, name)
    audio = importlib.import_module("faster_whisper.audio")
    assert audio.av is sys.modules["av"]


def test_pyav_metadata_does_not_ship_either():
    assert check().problems(GOOD_GPU + ["_internal/av-12.3.0.dist-info/METADATA"], "gpu")


# ---------------------------------------------------------------- the build script
@pytest.mark.parametrize("edition", ["gpu", "cpu"])
def test_the_installer_gets_the_version_and_edition(edition):
    import build_installer
    command = build_installer.iscc_command(edition, iscc="ISCC.exe")
    assert f"/DAppVersion={zeroflow.__version__}" in command
    assert f"/DEdition={edition}" in command
    assert command[-1].endswith("zeroflow.iss")


def test_the_build_stops_on_an_unexpected_gpl_package():
    """Only the GPL parts ADR 0003 accepted may pass the licence audit."""
    import build_installer
    assert build_installer.ACCEPTED_GPL == {"phonemizer-fork", "espeak-ng"}
    assert build_installer.unexpected_gpl(["phonemizer-fork", "espeak-ng"]) == []
    assert build_installer.unexpected_gpl(["phonemizer-fork", "x264"]) == ["x264"]


# ---------------------------------------------------------------- packaging/zeroflow.iss
def iss() -> str:
    with open(ISS, encoding="utf-8") as f:
        return f.read()


def test_it_installs_for_this_user_without_admin_rights():
    """Per-user, like the settings and the Start-with-Windows key: no UAC prompt, and
    the program folder can be written to."""
    text = iss()
    assert re.search(r"^PrivilegesRequired=lowest\s*$", text, re.M)
    assert "{autopf}" in text or "{localappdata}" in text


def test_both_editions_share_one_app_id():
    """Installing the other edition replaces the first instead of adding a second copy."""
    ids = re.findall(r"^AppId=(.+)$", iss(), re.M)
    assert len(ids) == 1 and "Edition" not in ids[0]


def test_the_running_engine_is_detected_by_its_own_lock():
    """Inno Setup's AppMutex asks Windows for the Engine's single-instance mutex, so
    setup and the uninstaller wait for the Engine to exit instead of failing on files
    in use."""
    match = re.search(r"^AppMutex=(.+)$", iss(), re.M)
    assert match
    for role in ("dictation", "reader"):
        assert signals.instance_mutex_name(role).removeprefix("Local\\") in match.group(1)


def test_the_uninstaller_asks_before_deleting_data():
    text = iss()
    assert "--remove-startup" in text and "--remove-data" in text
    assert re.search(r"MsgBox\(.*(MB_YESNO|mbConfirmation)", text, re.S)
    # "No" is the default answer: an Enter never deletes anything.
    assert "MB_DEFBUTTON2" in text


def test_the_notices_and_licence_ship_with_the_program():
    text = iss()
    assert "THIRD-PARTY-NOTICES.txt" in text and "LICENSE" in text


# ---------------------------------------------------------------- the benchmark fix
def test_the_load_benchmark_forces_the_cpu_through_a_settings_file():
    """ADR 0002: settings come only from the settings file, so READER_DEVICE in the
    environment was ignored and "reader-cpu" measured the graphics card."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "bench"))
    import measure_load
    for name, (_, env) in measure_load.PARTS.items():
        assert not set(env) & set(settings.SPEC), name
    assert measure_load.PART_SETTINGS["reader-cpu"] == {"READER_DEVICE": "cpu"}
