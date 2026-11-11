"""Every model is downloaded at a fixed revision, not whatever was uploaded last.

The speech model, the reader's voice and the built-in AI were each fetched from the
Hugging Face Hub at its latest revision. A changed or tampered upload would then be
downloaded and run by the next fresh install — the voice model's weights are loaded
with torch. Now each model the engine names is pinned to a commit
(zeroflow/models.py), like the llama.cpp build is (llm/llama_runtime.BUILD).
"""
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import models, stt
from zeroflow.llm import builtin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHA = re.compile(r"^[0-9a-f]{40}$")


class TestTheTable(unittest.TestCase):
    def test_every_revision_is_a_full_commit(self):
        for repo, sha in models.REVISIONS.items():
            self.assertRegex(sha, SHA, repo)

    def test_a_repo_nobody_pinned_has_none(self):
        self.assertIsNone(models.revision("someone/their-own-model"))

    def test_every_model_the_guides_and_presets_name_is_pinned(self):
        named = set()
        for folder in ("presets", "docs", "."):
            for name in os.listdir(os.path.join(ROOT, folder)):
                if name.endswith((".env", ".md", ".example")):
                    with open(os.path.join(ROOT, folder, name), encoding="utf-8") as f:
                        text = f.read()
                    named |= set(re.findall(r'WHISPER_MODEL_NAME="?([\w./-]+)', text))
                    named |= set(re.findall(r'AI_BUILTIN_REPO="?([\w./-]+)', text))
        self.assertTrue(named)
        for name in named:
            self.assertIsNotNone(models.revision(stt.whisper_repo(name) or name), name)


WHISPER_FOLDER = ("config.json", "preprocessor_config.json", "model.bin", "tokenizer.json",
                  "vocabulary.json")


class TestWhisper(unittest.TestCase):
    def model_folder(self, files=WHISPER_FOLDER):
        folder = tempfile.mkdtemp(prefix="zeroflow-whisper-")
        self.addCleanup(shutil.rmtree, folder, True)
        for name in files:
            with open(os.path.join(folder, name), "w") as f:
                f.write("x")
        return folder

    def resolve(self, name, cached=True, folder=None):
        calls = []
        folder = folder or self.model_folder()

        def fake_download(repo, **kwargs):
            calls.append((repo, kwargs))
            if kwargs.get("local_files_only") and not cached:
                raise FileNotFoundError("not cached")
            return folder
        with mock.patch.object(stt, "WHISPER_MODEL_NAME", name), \
             mock.patch.object(stt, "snapshot_download", side_effect=fake_download), \
             mock.patch("sys.stdout"):
            self.assertEqual(stt.resolve_whisper_model(), folder)
        return calls

    def test_a_cached_folder_missing_a_file_is_completed(self):
        """Live test, 2026-11-11: config.json vanished from the cached large-v3 folder,
        and every dictation failed (type_error.305) for days, on the CPU as well, because
        the cached folder was used as it was. A missing file is now fetched again."""
        incomplete = self.model_folder([f for f in WHISPER_FOLDER if f != "config.json"])
        calls = self.resolve("large-v3", folder=incomplete)
        self.assertEqual(len(calls), 2)
        self.assertFalse(calls[1][1].get("local_files_only"))
        self.assertEqual(calls[1][1]["revision"], models.REVISIONS["Systran/faster-whisper-large-v3"])

    def test_an_empty_file_counts_as_missing(self):
        folder = self.model_folder()
        open(os.path.join(folder, "model.bin"), "w").close()
        self.assertEqual(stt.missing_whisper_files(folder), ["model.bin"])

    def test_a_complete_folder_is_used_without_the_network(self):
        (_, kwargs), = self.resolve("large-v3")
        self.assertTrue(kwargs["local_files_only"])

    def test_a_short_name_is_fetched_at_its_pinned_revision(self):
        (repo, kwargs), = self.resolve("large-v3")
        self.assertEqual(repo, "Systran/faster-whisper-large-v3")
        self.assertEqual(kwargs["revision"], models.REVISIONS[repo])
        self.assertTrue(kwargs["local_files_only"])

    def test_a_download_is_pinned_too(self):
        calls = self.resolve("mobiuslabsgmbh/faster-whisper-large-v3-turbo", cached=False)
        self.assertEqual(len(calls), 2)
        for repo, kwargs in calls:
            self.assertEqual(kwargs["revision"], models.REVISIONS[repo])
        self.assertFalse(calls[1][1].get("local_files_only"))

    def test_only_the_files_whisper_needs_are_fetched(self):
        (_, kwargs), = self.resolve("small")
        self.assertIn("model.bin", kwargs["allow_patterns"])

    def test_a_local_folder_is_used_as_it_is(self):
        with mock.patch.object(stt, "WHISPER_MODEL_NAME", ROOT), \
             mock.patch.object(stt, "snapshot_download") as download:
            self.assertEqual(stt.resolve_whisper_model(), ROOT)
        download.assert_not_called()


class TestBuiltinAI(unittest.TestCase):
    def test_the_gguf_is_fetched_at_its_pinned_revision(self):
        with mock.patch("huggingface_hub.hf_hub_download", return_value="m.gguf") as get:
            builtin._model_path()
        self.assertEqual(get.call_args.kwargs["revision"],
                         models.REVISIONS[builtin.AI_BUILTIN_REPO])

    def test_a_first_download_is_pinned_too(self):
        with mock.patch("huggingface_hub.hf_hub_download",
                        side_effect=[FileNotFoundError("not cached"), "m.gguf"]) as get, \
             mock.patch("sys.stdout"):
            builtin._model_path()
        for call in get.call_args_list:
            self.assertEqual(call.kwargs["revision"], models.REVISIONS[builtin.AI_BUILTIN_REPO])


class TestReaderVoice(unittest.TestCase):
    def test_kokoro_files_come_from_the_pinned_revision(self):
        from reader import voice_engine
        with mock.patch("huggingface_hub.try_to_load_from_cache", return_value=None) as cached, \
             mock.patch("huggingface_hub.hf_hub_download", return_value="x") as get, \
             mock.patch("sys.stdout"):
            voice_engine._model_file("config.json")
        pinned = models.REVISIONS[voice_engine.REPO_ID]
        self.assertEqual(cached.call_args.kwargs["revision"], pinned)
        self.assertEqual(get.call_args.kwargs["revision"], pinned)


if __name__ == "__main__":
    unittest.main()
