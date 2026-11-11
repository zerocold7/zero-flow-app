"""The first-run wizard (zeroflow/first_run.py, zeroflow/wizard.py): when it runs, what it
recommends, where models go, downloads, the mic and AI tests, and where the key goes.
Offscreen, logic not pixels. Nothing here touches the network, a microphone or the real
Credential Manager: each is handed in."""
import json
import os
import shutil
import subprocess
import sys
import threading
import time

import numpy as np
import pytest
from PySide6.QtCore import Qt

from zeroflow import credentials, first_run, i18n, paths, settings, storage
from zeroflow.settings_window import SettingsWindow

SECRET = "sk-wizard-0123456789-SECRET"
FACTS = {"windows": True, "os": "Windows 11", "python": "3.12.8", "cpu": "Test CPU",
         "threads": 8, "ram_gb": 16.0,
         "gpus": [{"name": "NVIDIA GeForce RTX 4060 Laptop", "vram_gb": 8.0,
                   "vendor": "nvidia", "dedicated": True}]}


class FakeStartup:
    on = False

    def get(self):
        return self.on

    def set(self, on):
        self.on = on


def fake_fetch(item, cache_dir, on_bytes):
    """Writes the item as one finished file, reporting its bytes in four steps."""
    target = os.path.join(cache_dir, item.name.replace("/", "--"))
    with open(target + ".incomplete", "wb") as f:
        for _ in range(4):
            f.write(b"x" * 10)
            on_bytes(10)
    os.replace(target + ".incomplete", target)


@pytest.fixture
def wizard(qtbot, tmp_path):
    from zeroflow.wizard import SetupWizard
    i18n.choose("en")
    calls = {"pause": 0, "resume": 0, "recorded": [], "asked": []}
    store = credentials.MemoryStore()

    def record(device, seconds):
        calls["recorded"].append((device, seconds))
        return np.full(16000, 0.3, dtype=np.float32)

    def ask_ai(values, key, prompt):
        calls["asked"].append((values["AI_PROVIDER"], key))
        return "Hello."

    win = SetupWizard(
        settings_path=str(tmp_path / "settings.json"), store=store,
        microphones=["Desk mic", "Headset"], startup=FakeStartup(),
        detect=lambda: FACTS, fetch=fake_fetch, record=record, ask_ai=ask_ai,
        runtime_installed=lambda variant: True, cached=lambda item, cache_dir: False,
        keys_pause=lambda: calls.__setitem__("pause", calls["pause"] + 1),
        keys_resume=lambda: calls.__setitem__("resume", calls["resume"] + 1),
        environ={"LOCALAPPDATA": str(tmp_path / "local")})
    qtbot.addWidget(win)
    win.calls, win.store, win.path = calls, store, str(tmp_path / "settings.json")
    yield win
    i18n.choose("en")


def saved(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ it runs only on a first start
def test_it_runs_when_there_is_no_settings_file_and_nothing_to_migrate(tmp_path):
    old, data = tmp_path / "program", tmp_path / "data"
    old.mkdir(), data.mkdir()
    assert first_run.needs_setup(str(data / "settings.json"), str(old)) is True


def test_a_settings_file_means_no_wizard(tmp_path):
    (tmp_path / "settings.json").write_text("{}")
    assert first_run.needs_setup(str(tmp_path / "settings.json"), str(tmp_path)) is False


@pytest.mark.parametrize("name", first_run.OLD_FILES)
def test_any_old_file_to_migrate_means_no_wizard(tmp_path, name):
    (tmp_path / name).write_text("x")
    assert first_run.needs_setup(str(tmp_path / "none.json"), str(tmp_path)) is False


def test_the_old_files_are_the_ones_the_migration_moves():
    assert set(first_run.OLD_FILES) == {".env", *storage.DATA_NAMES}


# Every Windows user shares the program folder: another person's old files are not theirs.
ME, SOMEONE_ELSE = "S-1-5-21-1-2-3-1001", "S-1-5-21-1-2-3-1002"


def test_another_users_old_files_mean_the_wizard_not_the_migration(tmp_path):
    (tmp_path / ".env").write_text("x")
    (tmp_path / "flow_history.md").write_text("x")
    assert first_run.needs_setup(str(tmp_path / "none.json"), str(tmp_path),
                                 owner=lambda path: SOMEONE_ELSE, me=lambda: ME) is True


def test_one_file_of_another_user_is_enough_to_not_migrate(tmp_path):
    (tmp_path / ".env").write_text("x")
    (tmp_path / "flow_history.md").write_text("x")
    owners = {".env": ME, "flow_history.md": SOMEONE_ELSE}
    assert first_run.old_files_are_mine(
        str(tmp_path), owner=lambda path: owners[os.path.basename(path)], me=lambda: ME) is False


def test_own_old_files_migrate_and_an_unreadable_owner_counts_as_own(tmp_path):
    (tmp_path / ".env").write_text("x")
    assert first_run.old_files_are_mine(str(tmp_path), owner=lambda p: ME, me=lambda: ME)
    assert first_run.old_files_are_mine(str(tmp_path), owner=lambda p: None, me=lambda: ME)


def test_a_file_i_just_wrote_is_owned_by_me(tmp_path):
    (tmp_path / "mine.txt").write_text("x")
    me = first_run.current_user()
    assert me and me.startswith("S-1-5-")
    assert first_run.file_owner(str(tmp_path / "mine.txt")) == me


START = """
import json, os, sys
from zeroflow import credentials, first_run, paths
paths.BASE_DIR = sys.argv[1]
credentials.WindowsStore = credentials.MemoryStore
if len(sys.argv) > 2:                                  # the old files are someone else's
    first_run.file_owner = lambda path: "S-1-5-21-1-2-3-1002"
from zeroflow import settings
print(json.dumps({"setup": settings.NEEDS_SETUP,
                  "file": os.path.exists(os.environ["ZEROFLOW_SETTINGS"])}))
"""


def _start_engine_settings(old, data, someone_elses=False):
    env = dict(os.environ, ZEROFLOW_SETTINGS=str(data / "settings.json"))
    command = [sys.executable, "-c", START, str(old)] + (["other"] if someone_elses else [])
    out = subprocess.run(command, cwd=paths.BASE_DIR, env=env,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_a_first_start_with_nothing_to_migrate_writes_no_file_and_asks_for_setup(tmp_path):
    old, data = tmp_path / "program", tmp_path / "data"
    old.mkdir(), data.mkdir()
    assert _start_engine_settings(old, data) == {"setup": True, "file": False}


def test_a_first_start_with_an_old_env_migrates_and_skips_the_wizard(tmp_path):
    old, data = tmp_path / "program", tmp_path / "data"
    old.mkdir(), data.mkdir()
    (old / ".env").write_text("WHISPER_MODEL_NAME=small\n")
    assert _start_engine_settings(old, data) == {"setup": False, "file": True}
    assert _start_engine_settings(old, data) == {"setup": False, "file": True}   # and stays so


def test_another_users_old_env_is_not_migrated_on_a_new_account(tmp_path):
    old, data = tmp_path / "program", tmp_path / "data"
    old.mkdir(), data.mkdir()
    (old / ".env").write_text("WHISPER_MODEL_NAME=small\n")
    (old / "flow_history.md").write_text("someone else's dictations\n")
    assert _start_engine_settings(old, data, someone_elses=True) == {"setup": True, "file": False}
    assert os.listdir(data) == []                     # nothing of theirs was copied


# ------------------------------------------------------------------ Run setup again
def test_run_setup_again_in_settings_asks_for_the_wizard(qtbot, tmp_path):
    values, _ = settings.resolve({})
    values["DICTATION_ON"] = values["READER_ON"] = True
    path = tmp_path / "s.json"
    storage.save(str(path), {k: v for k, v in values.items() if k != "AI_API_KEY"})
    win = SettingsWindow(values, str(path), credentials.MemoryStore(), [], FakeStartup(),
                         lambda *a: None)
    qtbot.addWidget(win)
    win.show()
    with qtbot.waitSignal(win.setup_requested, timeout=500):
        qtbot.mouseClick(win.setup_again_button, Qt.LeftButton)
    assert not win.isVisible()                       # it closes, so its keys come back


def test_run_again_keeps_the_settings_the_wizard_does_not_ask_about(qtbot, wizard):
    storage.save(wizard.path, {"HOTKEY_EN_RAW": "f11", "KEEP_HISTORY": False})
    wizard.load_current()                             # what the app calls on "Run setup again"
    storage.update(wizard.path, {"DICTATION_ON": False})   # the tray, while it is open
    wizard.finish_setup()
    kept = saved(wizard.path)
    assert kept["HOTKEY_EN_RAW"] == "f11" and kept["KEEP_HISTORY"] is False
    assert kept["DICTATION_ON"] is False


# ------------------------------------------------------------------ the first screen, languages
def test_the_first_screen_has_the_interface_language_switch(wizard):
    assert wizard.currentId() == wizard.WELCOME
    options = [wizard.language_box.itemData(i) for i in range(wizard.language_box.count())]
    assert options == ["auto", "en", "ar"]


def test_arabic_switches_the_wizard_to_right_to_left_at_once(wizard):
    wizard.language_box.setCurrentIndex(wizard.language_box.findData("ar"))
    assert i18n.current() == "ar"
    assert wizard.layoutDirection() == Qt.RightToLeft
    assert wizard.windowTitle() == i18n.AR["wiz.title"]
    wizard.language_box.setCurrentIndex(wizard.language_box.findData("en"))
    assert wizard.layoutDirection() == Qt.LeftToRight


def test_the_chosen_language_is_saved(wizard):
    wizard.language_box.setCurrentIndex(wizard.language_box.findData("ar"))
    wizard.finish_setup()
    assert saved(wizard.path)["INTERFACE_LANGUAGE"] == "ar"


def test_every_wizard_text_has_an_arabic_table_entry():
    assert {k for k in i18n.EN if k.startswith("wiz.")} <= set(i18n.AR)


# ------------------------------------------------------------------ recommendations
def test_the_recommendation_is_detect_then_recommend_unchanged(monkeypatch):
    import check_hardware
    seen = {}

    def recommend(facts, tier=None):
        seen["facts"] = facts
        return "nvidia-laptop", {"WHISPER_MODEL_NAME": "small", "SOMETHING_ELSE": "x"}, ["why"]

    monkeypatch.setattr(check_hardware, "recommend", recommend)
    found = first_run.recommendation(detect=lambda: FACTS)
    assert seen["facts"] is FACTS
    assert found.tier == "nvidia-laptop" and found.reasons == ["why"]
    assert found.values == {"WHISPER_MODEL_NAME": "small"}     # only settings Zero- Flow has


def test_the_wizard_shows_and_uses_what_recommend_gives(wizard):
    import check_hardware
    tier, values, reasons = check_hardware.recommend(FACTS)
    wizard.next()                                       # to "This PC"
    assert wizard.currentId() == wizard.THIS_PC
    shown = wizard.this_pc_text()
    assert check_hardware.TIERS[tier] in shown
    assert all(reason in shown for reason in reasons)
    for name, value in values.items():
        if name in settings.SPEC:
            assert wizard.values[name] == value


# ------------------------------------------------------------------ the models folder
def test_the_models_folder_defaults_to_the_same_place_as_the_engine(wizard, tmp_path):
    assert wizard.models_dir_edit.text() == storage.default_models_dir(
        {"LOCALAPPDATA": str(tmp_path / "local")})


def test_the_chosen_models_folder_is_saved_as_models_dir(wizard, tmp_path):
    wizard.models_dir_edit.setText(str(tmp_path / "Models"))
    wizard.finish_setup()
    assert saved(wizard.path)["MODELS_DIR"] == str(tmp_path / "Models")


def test_downloads_go_to_the_chosen_folder(qtbot, wizard, tmp_path):
    wizard.models_dir_edit.setText(str(tmp_path / "Models"))
    wizard.downloads.start()
    qtbot.waitUntil(wizard.downloads.finished, timeout=3000)
    assert os.listdir(tmp_path / "Models" / "hub")


# ------------------------------------------------------------------ downloads
def test_the_list_follows_the_choices_and_shows_measured_sizes():
    items = first_run.downloads_for({"WHISPER_MODEL_NAME": "large-v3", "AI_PROVIDER": "builtin",
                                     "AI_BUILTIN_REPO": "google/gemma-4-E4B-it-qat-q4_0-gguf",
                                     "AI_BUILTIN_FILE": "gemma-4-E4B_q4_0-it.gguf",
                                     "READER_ON": True}, runtime="cuda", runtime_installed=False)
    names = [i.kind for i in items]
    assert names == ["whisper", "reader", "ai", "runtime"]
    assert all(i.size > 0 for i in items)
    no_ai = first_run.downloads_for({"WHISPER_MODEL_NAME": "small", "AI_PROVIDER": "ollama",
                                     "READER_ON": True}, runtime="cuda", runtime_installed=False)
    assert [i.kind for i in no_ai] == ["whisper", "reader"]   # Ollama brings its own model


def test_progress_is_reported_until_the_whole_size(qtbot, wizard):
    seen = {}
    wizard.downloads.progress.connect(
        lambda name, done, total: seen.setdefault(name, []).append(done))
    wizard.downloads.start()
    qtbot.waitUntil(wizard.downloads.finished, timeout=3000)
    assert set(seen) == {item.name for item in wizard.downloads.items}
    for steps in seen.values():                     # each item rises to its whole size
        assert steps[-1] == 40 and steps == sorted(steps)
    assert set(wizard.downloads.states().values()) == {"done"}


def test_a_cancelled_download_leaves_nothing_half_written(tmp_path):
    (tmp_path / "already-here.bin").write_bytes(b"kept")
    cancel = threading.Event()

    def fetch(item, cache_dir, on_bytes):
        os.makedirs(os.path.join(cache_dir, "blobs"), exist_ok=True)
        with open(os.path.join(cache_dir, "blobs", "abc.incomplete"), "wb") as f:
            f.write(b"half")
            cancel.set()
            on_bytes(4)                                 # the next report sees the cancel
            f.write(b"never")

    item = first_run.Item("whisper", "Systran/faster-whisper-small", "Speech model", 100)
    result = first_run.run_download(item, str(tmp_path), fetch, lambda done: None, cancel)
    assert result == "cancelled"
    assert sorted(os.listdir(tmp_path)) == ["already-here.bin"]


def test_a_failed_download_leaves_nothing_half_written_and_says_why(tmp_path):
    def fetch(item, cache_dir, on_bytes):
        with open(os.path.join(cache_dir, "model.bin.incomplete"), "wb") as f:
            f.write(b"half")
        raise OSError("connection reset")

    item = first_run.Item("whisper", "Systran/faster-whisper-small", "Speech model", 100)
    result = first_run.run_download(item, str(tmp_path), fetch, lambda done: None,
                                    threading.Event())
    assert result.startswith("failed") and "connection reset" in result
    assert os.listdir(tmp_path) == []


WRITER = """
import os, sys, time
folder = sys.argv[1]
os.makedirs(os.path.join(folder, "blobs"), exist_ok=True)
with open(os.path.join(folder, "blobs", "abc.incomplete"), "wb") as f:
    for _ in range(int(sys.argv[2])):
        f.write(b"x" * 1000)
        f.flush()
        time.sleep(0.02)
if sys.argv[3] == "fail":
    print("OSError: the Hub said no", file=sys.stderr)
    sys.exit(1)
os.replace(os.path.join(folder, "blobs", "abc.incomplete"), os.path.join(folder, "blobs", "abc"))
"""


def _real_fetch_with(monkeypatch, tmp_path, chunks, ending):
    """first_run.real_fetch, with its child replaced by a writer that needs no network."""
    real_popen = subprocess.Popen

    def popen(command, **kwargs):
        assert command[1:3] == ["-m", "zeroflow.fetch"]
        assert kwargs["env"]["HF_HUB_CACHE"] == str(tmp_path)
        return real_popen([sys.executable, "-c", WRITER, str(tmp_path), str(chunks), ending],
                          **kwargs)

    monkeypatch.setattr(first_run.subprocess, "Popen", popen)
    monkeypatch.setattr(first_run, "POLL_SECONDS", 0.02)
    return first_run.Item("whisper", "Systran/faster-whisper-small", "Speech model", 100,
                          first_run.WHISPER_PATTERNS)


def test_the_real_download_reports_what_its_child_writes(monkeypatch, tmp_path):
    item = _real_fetch_with(monkeypatch, tmp_path, 20, "ok")
    seen = []
    result = first_run.run_download(item, str(tmp_path), first_run.real_fetch, seen.append,
                                    threading.Event())
    assert result == "done" and seen[-1] == 20_000
    assert os.listdir(tmp_path / "blobs") == ["abc"]


def test_cancelling_the_real_download_stops_its_child_and_removes_its_files(monkeypatch, tmp_path):
    item = _real_fetch_with(monkeypatch, tmp_path, 500, "ok")         # ~10 s if never stopped
    cancel = threading.Event()

    def progress(done):
        if done > 2000:
            cancel.set()

    started = time.monotonic()
    result = first_run.run_download(item, str(tmp_path), first_run.real_fetch, progress, cancel)
    assert result == "cancelled"
    assert time.monotonic() - started < 5            # stopped, not left to finish its 10 s
    assert os.listdir(tmp_path) == []


def test_a_failed_real_download_says_what_the_child_said(monkeypatch, tmp_path):
    item = _real_fetch_with(monkeypatch, tmp_path, 3, "fail")
    result = first_run.run_download(item, str(tmp_path), first_run.real_fetch,
                                    lambda done: None, threading.Event())
    assert result == "failed: OSError: the Hub said no"
    assert os.listdir(tmp_path) == []


def test_the_runtime_download_reports_progress_and_a_cancel_installs_nothing(monkeypatch, tmp_path):
    import hashlib
    import io
    import zipfile

    from zeroflow.llm import llama_runtime as rt
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        z.writestr("llama-server.exe", b"MZ" + os.urandom(3 << 20))
    archive = data.getvalue()
    monkeypatch.setattr(rt, "RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setitem(rt.ARCHIVES, "cpu", [("fake.zip", hashlib.sha256(archive).hexdigest())])

    class Response(io.BytesIO):
        headers = {"Content-Length": str(len(archive))}

    monkeypatch.setattr(rt.urllib.request, "urlopen", lambda url, timeout: Response(archive))
    seen = []
    rt.install("cpu", progress=seen.append)
    assert sum(seen) == len(archive) and rt.installed("cpu")

    shutil.rmtree(rt.variant_dir("cpu"))

    def stop(count):
        raise first_run.Cancelled()
    with pytest.raises(first_run.Cancelled):
        rt.install("cpu", progress=stop)
    assert not rt.installed("cpu") and not os.path.exists(rt.variant_dir("cpu"))


def test_cancel_in_the_wizard_stops_the_download(qtbot, wizard):
    started = threading.Event()

    def slow(item, cache_dir, on_bytes):
        started.set()
        for _ in range(500):
            on_bytes(1)
            threading.Event().wait(0.01)

    wizard.downloads.fetch = slow
    wizard.downloads.start()
    started.wait(2)
    wizard.downloads.cancel()
    qtbot.waitUntil(lambda: not wizard.downloads.running(), timeout=3000)
    assert "cancelled" in wizard.downloads.states().values()


def test_a_model_already_in_the_folder_is_not_downloaded_again(qtbot, wizard):
    fetched = []
    wizard.downloads.cached = lambda item, cache_dir: item.kind == "whisper"
    wizard.downloads.fetch = lambda item, cache_dir, on_bytes: fetched.append(item.kind)
    wizard.downloads.start()
    qtbot.waitUntil(wizard.downloads.finished, timeout=3000)
    assert "whisper" not in fetched


# ------------------------------------------------------------------ mic test, AI test
def test_the_mic_test_passes_on_a_voice_and_records_from_the_chosen_mic(wizard):
    wizard.mic_box.setCurrentIndex(wizard.mic_box.findData("Headset"))
    result = wizard.test_microphone()
    assert result.ok and wizard.calls["recorded"][-1][0] == "Headset"
    assert wizard.mic_result.text() == f"Passed: {result.message}"


@pytest.mark.parametrize("record, why", [
    (lambda device, seconds: np.zeros(16000, dtype=np.float32), "silence"),
    (lambda device, seconds: (_ for _ in ()).throw(OSError("device unavailable")), "error"),
])
def test_the_mic_test_fails_clearly(record, why):
    result = first_run.mic_test(record, "Desk mic")
    assert not result.ok and result.message
    if why == "error":
        assert "device unavailable" in result.message


def test_the_ai_test_passes_on_an_answer(wizard):
    result = wizard.test_ai()
    assert result.ok and wizard.calls["asked"] == [("builtin", None)]
    assert wizard.ai_result.text() == f"Passed: {result.message}"


def test_the_ai_test_hands_the_typed_key_over_without_saving_it(wizard):
    wizard.provider_page.choose_preset("claude")
    wizard.provider_page.key_edit.setText(SECRET)
    wizard.test_ai()
    assert wizard.calls["asked"] == [("custom", SECRET)]
    assert wizard.store.get("https://api.anthropic.com") is None     # only Finish stores it
    assert not os.path.exists(wizard.path)


def test_the_ai_tests_settings_file_never_holds_the_key(monkeypatch):
    """real_ask writes the wizard's choices to a temporary file; the key goes on stdin."""
    written, sent = [], []

    class Child:
        returncode = 0

        def __init__(self, *args, **kwargs):
            path = kwargs["env"]["ZEROFLOW_SETTINGS"]
            with open(path, encoding="utf-8") as f:
                written.append(f.read())

        def communicate(self, data, timeout):
            sent.append(data)
            return '{"answer": "Hello.", "why": null}\n', ""

    monkeypatch.setattr(first_run.subprocess, "Popen", Child)
    monkeypatch.setattr("zeroflow.signals.bind_child_to_this_process", lambda child: None)
    values, _ = settings.resolve({})
    values["AI_API_KEY"] = SECRET                     # even if one slipped into the values
    assert first_run.real_ask(values, SECRET, "hello") == "Hello."
    assert SECRET not in written[0] and sent == [SECRET + "\n"]


@pytest.mark.parametrize("answer", [None, "", RuntimeError("server did not start")])
def test_the_ai_test_fails_clearly(answer):
    def ask(prompt):
        if isinstance(answer, Exception):
            raise answer
        return answer
    result = first_run.ai_test(ask)
    assert not result.ok and result.message
    if isinstance(answer, Exception):
        assert "server did not start" in result.message


# ------------------------------------------------------------------ the API key
def test_the_api_key_goes_only_to_credential_manager(wizard, tmp_path):
    wizard.provider_page.choose_preset("claude")
    wizard.provider_page.key_edit.setText(SECRET)
    wizard.finish_setup()
    assert wizard.store.get("https://api.anthropic.com") == SECRET
    for root, _, files in os.walk(tmp_path):
        for name in files:
            with open(os.path.join(root, name), "rb") as f:
                assert SECRET.encode() not in f.read(), name
    assert "AI_API_KEY" not in saved(wizard.path)


def test_a_key_that_cannot_be_stored_writes_no_settings_file(wizard):
    class Broken(credentials.MemoryStore):
        def set(self, address, key):
            raise OSError(5, "no")
    wizard.store = Broken()
    wizard.provider_page.choose_preset("claude")
    wizard.provider_page.key_edit.setText(SECRET)
    assert wizard.finish_setup() is False
    assert not os.path.exists(wizard.path)            # so the wizard runs again next start
    assert SECRET not in wizard.status.text()


# ------------------------------------------------------------------ keys and the end
def test_the_program_lets_go_of_its_keys_while_the_wizard_is_open(wizard):
    wizard.show()
    wizard.show()
    assert wizard.calls["pause"] == 1
    wizard.reject()
    assert wizard.calls["resume"] == 1


def test_finishing_writes_one_complete_settings_file_and_asks_for_a_restart(qtbot, wizard):
    with qtbot.waitSignal(wizard.completed, timeout=500):
        assert wizard.finish_setup() is True
    written = saved(wizard.path)
    assert set(written) >= {"MODELS_DIR", "INTERFACE_LANGUAGE", "WHISPER_MODEL_NAME",
                            "AI_PROVIDER", "MICROPHONE"}
    values, problems = settings.resolve({k: str(v) for k, v in written.items()})
    assert problems == []                             # every value passes the Engine's checks


def test_closing_the_wizard_on_a_first_start_writes_nothing(wizard):
    wizard.reject()
    assert not os.path.exists(wizard.path)
