"""Phase 7: what the uninstaller removes (zeroflow/uninstall.py, run by the Inno Setup
uninstaller as `ZeroFlow.exe --remove-data` or `--remove-startup`).

The uninstaller asks first. "Keep my data" removes only the Start-with-Windows entry
(a Run key pointing at a deleted program would fail at every sign-in). "Delete my data"
also removes Zero- Flow's own folders and its API keys, and never a models folder the
user chose (MODELS_DIR = F:\\HuggingFace is shared with other programs).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import credentials, uninstall


class FakeRunKey:
    def __init__(self, on=True):
        self.on = on

    def get(self):
        return self.on

    def set(self, on):
        self.on = on


def layout(tmp_path, models_dir=None):
    roaming = tmp_path / "Roaming" / "ZeroFlow"
    local = tmp_path / "Local" / "ZeroFlow"
    for folder in (roaming, local / "logs", local / "models", local / "runtime"):
        folder.mkdir(parents=True)
    (roaming / "settings.json").write_text("{}")
    (roaming / "vocabulary.txt").write_text("Zero")
    (local / "logs" / "flow_debug.log").write_text("log")
    environ = {"APPDATA": str(tmp_path / "Roaming"), "LOCALAPPDATA": str(tmp_path / "Local")}
    return roaming, local, environ


def test_keeping_data_removes_only_the_start_with_windows_entry(tmp_path):
    roaming, local, environ = layout(tmp_path)
    run, store = FakeRunKey(), credentials.MemoryStore()
    store.set("https://api.anthropic.com", "sk-x")
    uninstall.remove_startup(run)
    assert run.on is False
    assert roaming.exists() and local.exists() and store.get("https://api.anthropic.com")


def test_deleting_data_removes_both_folders_and_the_keys(tmp_path):
    roaming, local, environ = layout(tmp_path)
    run, store = FakeRunKey(), credentials.MemoryStore()
    store.set("https://api.anthropic.com", "sk-x")
    store.set("http://127.0.0.1:8080", "sk-y")
    uninstall.remove_data(environ, {"MODELS_DIR": str(local / "models")}, store, run)
    assert not roaming.exists() and not local.exists()
    assert store.addresses() == []
    assert run.on is False


def test_a_models_folder_the_user_chose_is_never_deleted(tmp_path):
    roaming, local, environ = layout(tmp_path)
    shared = tmp_path / "HuggingFace"
    (shared / "hub").mkdir(parents=True)
    (shared / "hub" / "other-programs-model.bin").write_text("x")
    uninstall.remove_data(environ, {"MODELS_DIR": str(shared)}, credentials.MemoryStore(),
                          FakeRunKey())
    assert (shared / "hub" / "other-programs-model.bin").exists()
    assert not roaming.exists()


def test_the_report_says_what_was_kept(tmp_path):
    roaming, local, environ = layout(tmp_path)
    shared = tmp_path / "HuggingFace"
    shared.mkdir()
    report = uninstall.remove_data(environ, {"MODELS_DIR": str(shared)},
                                   credentials.MemoryStore(), FakeRunKey())
    assert str(shared) in report.kept and str(roaming) in report.removed


def test_only_zero_flow_folders_are_touched(tmp_path):
    """Never the parent folders, whatever the environment says."""
    roaming, local, environ = layout(tmp_path)
    neighbour = tmp_path / "Roaming" / "SomeOtherApp"
    neighbour.mkdir()
    uninstall.remove_data(environ, {}, credentials.MemoryStore(), FakeRunKey())
    assert neighbour.exists() and (tmp_path / "Roaming").exists()


def test_missing_folders_are_not_an_error(tmp_path):
    environ = {"APPDATA": str(tmp_path / "a"), "LOCALAPPDATA": str(tmp_path / "b")}
    report = uninstall.remove_data(environ, {}, credentials.MemoryStore(), FakeRunKey())
    assert report.failed == []


def test_a_file_in_use_is_reported_not_raised(tmp_path, monkeypatch):
    roaming, local, environ = layout(tmp_path)

    def busy(path, *args, **kwargs):
        raise PermissionError("in use")
    monkeypatch.setattr(uninstall.shutil, "rmtree", busy)
    report = uninstall.remove_data(environ, {}, credentials.MemoryStore(), FakeRunKey())
    assert str(roaming) in report.failed


def test_the_settings_are_read_from_the_settings_file(tmp_path):
    roaming, local, environ = layout(tmp_path)
    (roaming / "settings.json").write_text('{"MODELS_DIR": "D:\\\\Models"}')
    assert uninstall.models_dir(environ) == "D:\\Models"


def test_memory_store_lists_its_addresses():
    store = credentials.MemoryStore()
    store.set("b", "1")
    store.set("a", "2")
    assert sorted(store.addresses()) == ["a", "b"]


def test_the_windows_store_can_list_zero_flow_keys():
    """CredEnumerateW with the "ZeroFlow:*" filter; checked for real in the Sandbox gate."""
    assert callable(getattr(credentials.WindowsStore, "addresses", None))


def test_a_models_folder_inside_zero_flows_own_is_not_reported_as_kept(tmp_path):
    roaming, local, environ = layout(tmp_path)
    report = uninstall.remove_data(environ, {"MODELS_DIR": str(local / "models")},
                                   credentials.MemoryStore(), FakeRunKey())
    assert report.kept == [] and str(local) in report.removed


def test_a_relative_folder_in_the_environment_is_never_used(tmp_path, monkeypatch):
    """A relative APPDATA would point into the folder the uninstaller runs in."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "relative" / "ZeroFlow").mkdir(parents=True)
    environ = {"APPDATA": "relative", "LOCALAPPDATA": "relative"}
    report = uninstall.remove_data(environ, {}, credentials.MemoryStore(), FakeRunKey())
    assert (tmp_path / "relative" / "ZeroFlow").exists() and report.removed == []


def test_without_a_setting_the_default_models_folder_is_named(tmp_path):
    roaming, local, environ = layout(tmp_path)
    assert uninstall.models_dir(environ) == str(local / "models")


# ---------------------------------------------------------------- ZeroFlow.exe --remove-*
def test_other_arguments_start_the_engine(tmp_path):
    """Fakes only: with the flag check broken, a real run would delete this PC's data."""
    roaming, local, environ = layout(tmp_path)
    run = FakeRunKey()
    for argv in (["ZeroFlow.exe"], ["ZeroFlow.exe", "--child", "reader"]):
        assert uninstall.run(argv, environ, credentials.MemoryStore(), run) is None
    assert run.on is True and roaming.exists() and local.exists()


def test_remove_startup_touches_only_the_run_key(tmp_path):
    roaming, local, environ = layout(tmp_path)
    run = FakeRunKey()
    assert uninstall.run(["ZeroFlow.exe", "--remove-startup"], environ,
                         credentials.MemoryStore(), run) == 0
    assert run.on is False and roaming.exists() and local.exists()


def test_remove_data_removes_everything_and_says_so(tmp_path, capsys):
    roaming, local, environ = layout(tmp_path)
    run, store = FakeRunKey(), credentials.MemoryStore()
    store.set("https://api.anthropic.com", "sk-x")
    assert uninstall.run(["ZeroFlow.exe", "--remove-data"], environ, store, run) == 0
    assert not roaming.exists() and not local.exists()
    assert store.addresses() == [] and run.on is False
    assert f"Removed: {roaming}" in capsys.readouterr().out


def test_remove_data_exits_with_1_when_something_stays(tmp_path, monkeypatch):
    roaming, local, environ = layout(tmp_path)

    def busy(path, *args, **kwargs):
        raise PermissionError("in use")
    monkeypatch.setattr(uninstall.shutil, "rmtree", busy)
    assert uninstall.run(["ZeroFlow.exe", "--remove-data"], environ,
                         credentials.MemoryStore(), FakeRunKey()) == 1


def test_the_entry_point_hands_the_flags_over_before_the_engine(monkeypatch):
    import runpy
    from zeroflow import frozen

    def engine_started(argv):
        raise AssertionError("the uninstall step reached the Engine's start")
    monkeypatch.setattr(uninstall, "run", lambda argv: 0)
    monkeypatch.setattr(frozen, "run_child", engine_started)
    monkeypatch.setattr(sys, "argv", ["ZeroFlow.exe", "--remove-data"])
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        runpy.run_path(os.path.join(root, "zero_flow.py"), run_name="__main__")
    except SystemExit as stop:
        assert stop.code == 0
    else:
        raise AssertionError("zero_flow.py did not exit")


def test_the_uninstaller_loads_neither_qt_nor_the_settings():
    """Importing zeroflow.settings reads, and can migrate, the settings file."""
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = ("import sys; from zeroflow import startup, uninstall; "
            "print(sorted(m for m in ('zeroflow.settings', 'PySide6') if m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True,
                         text=True, timeout=60).stdout
    assert out.strip() == "[]"
