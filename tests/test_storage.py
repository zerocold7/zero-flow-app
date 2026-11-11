"""Phase 5a: one settings file in %APPDATA%\\ZeroFlow, filled once from the old files.

Migration runs only when no settings file exists. It copies .env, flow_vocabulary.txt
and flow_history.md and never changes them. AI_API_KEY goes to Windows Credential
Manager under the provider's address, never into the settings file. The models folder
is a setting; a copy whose models already live elsewhere (HF_HOME) keeps them there.

The "real files" tests copy this PC's own .env, vocabulary and history into a temporary
folder and migrate the copies; they are skipped where those files do not exist. Nothing
here writes to the real %APPDATA%, and no value from .env is ever printed.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import credentials, paths, settings, storage

PROGRAM_DIR = paths.BASE_DIR
OLD_FILES = (".env", "flow_vocabulary.txt", "flow_history.md")
PLANTED_KEY = "sk-planted-" + "x" * 24


def fingerprint(path):
    """Content and modification time: "untouched" means both are the same."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest(), os.stat(path).st_mtime_ns


def tree(folder):
    """Every file under `folder` with its fingerprint."""
    found = {}
    for root, _, files in os.walk(folder):
        for name in files:
            path = os.path.join(root, name)
            found[os.path.relpath(path, folder)] = fingerprint(path)
    return found


class MigrationCase(unittest.TestCase):
    """An old program folder and an empty data folder, both temporary."""

    def setUp(self):
        self.old = tempfile.mkdtemp(prefix="zeroflow-old-")
        self.data = tempfile.mkdtemp(prefix="zeroflow-data-")
        self.addCleanup(shutil.rmtree, self.old, True)
        self.addCleanup(shutil.rmtree, self.data, True)
        self.keys = credentials.MemoryStore()

    def write_old(self, name, text):
        with open(os.path.join(self.old, name), "w", encoding="utf-8", newline="") as f:
            f.write(text)

    def migrate(self, environ=None):
        return storage.migrate(self.old, self.data, self.keys,
                               environ={} if environ is None else environ)

    def saved(self):
        with open(os.path.join(self.data, storage.SETTINGS_NAME), encoding="utf-8") as f:
            return json.load(f)


# ---------------------------------------------------------------- this PC's real files
def real_files_present():
    return all(os.path.exists(os.path.join(PROGRAM_DIR, name)) for name in OLD_FILES)


@unittest.skipUnless(real_files_present(), "this PC has no old .env, vocabulary and history")
class TestRealFiles(MigrationCase):
    def setUp(self):
        super().setUp()
        for name in OLD_FILES:
            shutil.copy2(os.path.join(PROGRAM_DIR, name), self.old)

    def test_every_setting_in_the_real_env_migrates_with_the_value_the_engine_uses(self):
        result = self.migrate()
        self.assertTrue(result.ran)
        saved = self.saved()
        names = storage.env_names(os.path.join(self.old, ".env"))
        self.assertTrue(names)
        for name in names:
            if name == storage.KEY_NAME:            # goes to Credential Manager instead
                continue
            if name in settings.RETIRED:            # now a constant in the code
                self.assertNotIn(name, saved)
                continue
            self.assertIn(name, saved, f"{name} was not migrated")
            # The value the engine reads from .env today (same checks, same defaults).
            self.assertEqual(saved[name], storage.read_from_env(os.path.join(self.old, ".env"), name),
                             f"{name} changed in the migration")
        self.assertEqual(result.problems, [])

    def test_the_real_vocabulary_and_history_are_copied_byte_for_byte(self):
        self.migrate()
        for name in ("flow_vocabulary.txt", "flow_history.md"):
            self.assertEqual(fingerprint(os.path.join(self.data, storage.DATA_NAMES[name]))[0],
                             fingerprint(os.path.join(self.old, name))[0], name)

    def test_the_real_old_files_are_left_untouched(self):
        before = tree(self.old)
        self.migrate()
        self.migrate()
        self.assertEqual(tree(self.old), before)

    def test_a_second_run_changes_nothing(self):
        self.migrate()
        after_first = tree(self.data)
        result = self.migrate()
        self.assertFalse(result.ran)
        self.assertEqual(tree(self.data), after_first)

    @unittest.skipUnless(os.environ.get("HF_HOME"), "no HF_HOME on this PC")
    def test_the_models_stay_where_this_copy_keeps_them(self):
        self.migrate(environ=dict(os.environ))
        self.assertEqual(os.path.normcase(self.saved()["MODELS_DIR"]),
                         os.path.normcase(os.environ["HF_HOME"]))


# ---------------------------------------------------------------- when migration runs
class TestWhenItRuns(MigrationCase):
    def test_it_runs_only_when_there_is_no_settings_file(self):
        self.write_old(".env", "WHISPER_MODEL_NAME=small\n")
        self.assertTrue(self.migrate().ran)
        self.write_old(".env", "WHISPER_MODEL_NAME=medium\n")    # edited afterwards
        self.assertFalse(self.migrate().ran)
        self.assertEqual(self.saved()["WHISPER_MODEL_NAME"], "small")   # .env is ignored now

    def test_nothing_to_migrate_still_writes_a_settings_file_of_defaults(self):
        result = self.migrate()
        self.assertTrue(result.ran)
        self.assertEqual(self.saved()["WHISPER_MODEL_NAME"], "large-v3")
        self.assertFalse(os.path.exists(os.path.join(self.data, storage.DATA_NAMES["flow_history.md"])))

    def test_the_vocabulary_and_history_are_copied_under_their_new_names(self):
        self.write_old("flow_vocabulary.txt", "Kokoro\nChromaDB\n")
        self.write_old("flow_history.md", "[12:00:00] [EN_RAW]\nمرحبا\n\n")
        self.migrate()
        for old, new in storage.DATA_NAMES.items():
            self.assertTrue(os.path.exists(os.path.join(self.data, new)), f"{new} was not copied")
            with open(os.path.join(self.old, old), "rb") as f, \
                 open(os.path.join(self.data, new), "rb") as g:
                self.assertEqual(g.read(), f.read(), new)

    def test_a_failed_copy_leaves_no_settings_file_so_the_next_start_tries_again(self):
        self.write_old("flow_vocabulary.txt", "Kokoro\n")
        with mock.patch.object(storage.shutil, "copy2", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.migrate()
        self.assertFalse(os.path.exists(os.path.join(self.data, storage.SETTINGS_NAME)))
        self.assertTrue(self.migrate().ran)

    def test_a_bad_value_takes_the_default_and_is_reported_by_name(self):
        self.write_old(".env", "MAX_RECORDING_SECONDS=five\n")
        result = self.migrate()
        self.assertEqual(self.saved()["MAX_RECORDING_SECONDS"], 300)
        self.assertTrue(any("MAX_RECORDING_SECONDS" in p for p in result.problems))

    def test_a_retired_setting_is_left_out_without_a_complaint(self):
        self.write_old(".env", "FALLBACK_LLM=gemma2:27b\nREADER_BATCH_CHARS=300\nHOTKEY_PANIC=esc\n")
        result = self.migrate()
        self.assertEqual(result.problems, [])
        self.assertFalse(set(settings.RETIRED) & set(self.saved()))

    def test_a_name_the_engine_does_not_know_is_reported_not_kept(self):
        self.write_old(".env", "WHISPER_MODLE_NAME=small\n")
        result = self.migrate()
        self.assertNotIn("WHISPER_MODLE_NAME", self.saved())
        self.assertTrue(any("WHISPER_MODLE_NAME" in p for p in result.problems))


# ---------------------------------------------------------------- the models folder
class TestModelsFolder(MigrationCase):
    def test_without_hf_home_the_default_is_under_localappdata(self):
        self.migrate(environ={"LOCALAPPDATA": r"C:\Users\someone\AppData\Local"})
        self.assertEqual(self.saved()["MODELS_DIR"],
                         r"C:\Users\someone\AppData\Local\ZeroFlow\models")

    def test_hf_home_becomes_the_models_folder(self):
        self.migrate(environ={"HF_HOME": r"F:\HuggingFace", "LOCALAPPDATA": r"C:\x"})
        self.assertEqual(self.saved()["MODELS_DIR"], r"F:\HuggingFace")

    def test_the_engine_points_hugging_face_at_the_models_folder(self):
        environ = {}
        storage.apply_models_dir({"MODELS_DIR": r"F:\HuggingFace"}, environ)
        self.assertEqual(environ["HF_HOME"], r"F:\HuggingFace")


# ---------------------------------------------------------------- the API key
class TestApiKey(MigrationCase):
    def test_the_key_goes_to_credential_manager_under_the_provider_address(self):
        self.write_old(".env", f"AI_PROVIDER=openai\nAI_URL=https://api.example.com/v1/chat/completions\n"
                               f"AI_API_KEY={PLANTED_KEY}\n")
        result = self.migrate()
        self.assertEqual(self.keys.get("https://api.example.com"), PLANTED_KEY)
        self.assertTrue(result.key_moved)

    def test_claude_keys_are_stored_under_anthropics_address(self):
        self.write_old(".env", f"AI_PROVIDER=claude\nAI_API_KEY={PLANTED_KEY}\n")
        self.migrate()
        self.assertEqual(self.keys.get("https://api.anthropic.com"), PLANTED_KEY)

    def test_the_address_is_the_server_not_the_path(self):
        self.assertEqual(credentials.address_of("https://API.example.com:8443/v1/chat/completions"),
                         "https://api.example.com:8443")
        self.assertEqual(credentials.address_of("https://api.example.com/v2/other"),
                         credentials.address_of("https://api.example.com/v1/chat/completions"))

    def test_the_key_is_never_written_to_any_file_in_the_data_folder(self):
        self.write_old(".env", f"AI_PROVIDER=claude\nAI_API_KEY={PLANTED_KEY}\n")
        try:
            self.migrate()
        except ValueError as e:                  # storage.save's own refusal
            self.fail(f"the key was on its way into the settings file: {e}")
        for name in tree(self.data):
            with open(os.path.join(self.data, name), "rb") as f:
                self.assertNotIn(PLANTED_KEY.encode(), f.read(), name)
        self.assertNotIn("AI_API_KEY", self.saved())

    def test_the_old_env_still_holds_the_key_and_the_notice_says_so(self):
        self.write_old(".env", f"AI_PROVIDER=claude\nAI_API_KEY={PLANTED_KEY}\n")
        before = fingerprint(os.path.join(self.old, ".env"))
        result = self.migrate()
        self.assertEqual(fingerprint(os.path.join(self.old, ".env")), before)
        self.assertTrue(result.key_left_in_env)

    def test_a_second_run_does_not_touch_the_stored_key(self):
        self.write_old(".env", f"AI_PROVIDER=claude\nAI_API_KEY={PLANTED_KEY}\n")
        self.migrate()
        self.keys.set("https://api.anthropic.com", "changed-in-the-window")
        self.migrate()
        self.assertEqual(self.keys.get("https://api.anthropic.com"), "changed-in-the-window")

    def test_remove_it_deletes_only_the_key_line(self):
        self.write_old(".env", f"# my settings\r\nAI_PROVIDER=claude\r\nAI_API_KEY = {PLANTED_KEY}\r\n"
                               f"HOTKEY_READ=f4\r\n")
        self.assertTrue(storage.remove_key_line(os.path.join(self.old, ".env")))
        with open(os.path.join(self.old, ".env"), "rb") as f:
            self.assertEqual(f.read(), b"# my settings\r\nAI_PROVIDER=claude\r\nHOTKEY_READ=f4\r\n")

    def test_remove_it_with_no_key_line_changes_nothing(self):
        self.write_old(".env", "HOTKEY_READ=f4\n")
        before = fingerprint(os.path.join(self.old, ".env"))
        self.assertFalse(storage.remove_key_line(os.path.join(self.old, ".env")))
        self.assertEqual(fingerprint(os.path.join(self.old, ".env")), before)

    def test_a_blank_key_moves_nothing(self):
        self.write_old(".env", "AI_PROVIDER=claude\nAI_API_KEY=\n")
        result = self.migrate()
        self.assertFalse(result.key_moved)
        self.assertFalse(result.key_left_in_env)


@unittest.skipUnless(sys.platform == "win32", "Windows Credential Manager")
class TestWindowsCredentialManager(unittest.TestCase):
    """The real store, under a throwaway address that is deleted afterwards."""

    def test_a_key_is_written_read_back_and_deleted(self):
        store = credentials.WindowsStore()
        address = f"https://zeroflow-test-{uuid.uuid4().hex}.invalid"
        self.addCleanup(store.delete, address)
        self.assertIsNone(store.get(address))
        store.set(address, PLANTED_KEY)
        self.assertEqual(store.get(address), PLANTED_KEY)
        store.delete(address)
        self.assertIsNone(store.get(address))


class TestTheFileItself(MigrationCase):
    def test_saving_a_key_into_the_file_is_refused(self):
        with self.assertRaises(ValueError):
            storage.save(os.path.join(self.data, storage.SETTINGS_NAME), {"AI_API_KEY": PLANTED_KEY})
        self.assertEqual(tree(self.data), {})


# ---------------------------------------------------------------- the engine's start
START = """
import json, sys
from zeroflow import credentials, paths
paths.BASE_DIR = sys.argv[1]                       # the old program folder
credentials.WindowsStore = credentials.MemoryStore # never the real Credential Manager
from zeroflow import settings
import huggingface_hub.constants
print(json.dumps({"problems": settings.problems, "whisper": settings.WHISPER_MODEL_NAME,
                  "key": settings.AI_API_KEY, "hf_home": huggingface_hub.constants.HF_HOME}))
"""


class TestTheEngineStart(MigrationCase):
    """A fresh Python each time, as the Engine starts: settings.py migrates on import."""

    def start(self):
        env = dict(os.environ, ZEROFLOW_SETTINGS=os.path.join(self.data, storage.SETTINGS_NAME),
                   HF_HOME=os.path.join(self.data, "hf-before"))
        out = subprocess.run([sys.executable, "-c", START, self.old], cwd=PROGRAM_DIR, env=env,
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr[-800:])
        return json.loads(out.stdout.strip().splitlines()[-1])

    def test_the_first_start_migrates_and_runs_on_the_old_values(self):
        self.write_old(".env", f"WHISPER_MODEL_NAME=small\nAI_PROVIDER=claude\nAI_API_KEY={PLANTED_KEY}\n")
        first = self.start()
        self.assertEqual(first["whisper"], "small")
        self.assertEqual(first["key"], PLANTED_KEY)
        self.assertTrue(any("Credential Manager" in p for p in first["problems"]))
        self.assertTrue(os.path.exists(os.path.join(self.data, storage.SETTINGS_NAME)))

    def test_the_next_start_reads_only_the_settings_file(self):
        self.write_old(".env", "WHISPER_MODEL_NAME=small\n")
        self.start()
        self.write_old(".env", "WHISPER_MODEL_NAME=medium\n")
        second = self.start()
        self.assertEqual(second["whisper"], "small")
        self.assertEqual(second["problems"], [])

    def test_hugging_face_looks_in_the_models_folder(self):
        storage.save(os.path.join(self.data, storage.SETTINGS_NAME), {"MODELS_DIR": r"F:\SomeModels"})
        self.assertEqual(self.start()["hf_home"], r"F:\SomeModels")


class TestAFailedFirstStart(unittest.TestCase):
    def test_the_engine_stops_and_says_why(self):
        with mock.patch.object(storage, "migrate", side_effect=OSError("access denied")):
            with self.assertRaises(RuntimeError) as raised:
                settings._first_start_migration()
        self.assertIn("access denied", str(raised.exception))


class TestHardwareCheckApply(MigrationCase):
    def test_apply_writes_into_the_settings_file_once_there_is_one(self):
        import check_hardware as hw
        target = os.path.join(self.data, storage.SETTINGS_NAME)
        storage.save(target, {"HOTKEY_READ": "f4", "WHISPER_MODEL_NAME": "large-v3"})
        env_before = fingerprint(hw.ENV_FILE) if os.path.exists(hw.ENV_FILE) else None
        with mock.patch.object(hw.zeroflow_paths, "settings_file", return_value=target):
            self.assertEqual(hw.apply({"WHISPER_MODEL_NAME": "small"}), target)
        self.assertEqual(storage.load(target), {"HOTKEY_READ": "f4", "WHISPER_MODEL_NAME": "small"})
        self.assertEqual(fingerprint(hw.ENV_FILE) if os.path.exists(hw.ENV_FILE) else None, env_before)


# ---------------------------------------------------------------- where things live
class TestPlaces(unittest.TestCase):
    def test_settings_and_data_live_in_appdata(self):
        with mock.patch.dict(os.environ, {"APPDATA": r"C:\Users\someone\AppData\Roaming"}):
            os.environ.pop("ZEROFLOW_SETTINGS", None)
            self.assertEqual(paths.data_dir(), r"C:\Users\someone\AppData\Roaming\ZeroFlow")
            self.assertEqual(paths.settings_file(),
                             r"C:\Users\someone\AppData\Roaming\ZeroFlow\settings.json")

    def test_a_developer_points_at_another_settings_file_with_one_variable(self):
        with mock.patch.dict(os.environ, {"ZEROFLOW_SETTINGS": r"D:\dev\settings.json"}):
            self.assertEqual(paths.settings_file(), r"D:\dev\settings.json")
            self.assertEqual(paths.data_dir(), r"D:\dev")

    def test_logs_go_to_localappdata(self):
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\someone\AppData\Local"}):
            os.environ.pop("ZEROFLOW_LOG_DIR", None)
            self.assertEqual(paths.log_dir(), r"C:\Users\someone\AppData\Local\ZeroFlow\logs")

    def test_settings_no_longer_read_env(self):
        """ADR 0002: .env is read once by the migration and never again."""
        with open(settings.__file__, encoding="utf-8") as f:
            self.assertNotIn("load_dotenv", f.read())


if __name__ == "__main__":
    unittest.main()
