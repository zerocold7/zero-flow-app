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
