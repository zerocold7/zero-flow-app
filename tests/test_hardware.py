"""Hardware tiers, presets and the Whisper device setting — what decides which models
a given PC runs.

check_hardware.py is standard-library only; these tests feed it made-up hardware, so
they pass on any machine and never touch the real .env.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import stt

import check_hardware as hw

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pc(*gpus, ram=32):
    """Made-up hardware facts: gpus are (name, vram_gb) pairs."""
    listed = []
    for name, vram in gpus:
        vendor, dedicated = hw.classify_gpu(name)
        listed.append({"name": name, "vram_gb": vram, "vendor": vendor, "dedicated": dedicated})
    return {"windows": True, "os": "Windows 11", "python": "3.12", "cpu": "test",
            "threads": 8, "ram_gb": ram, "gpus": listed}


class TestClassifyGpu(unittest.TestCase):
    def test_cards_and_built_in_graphics(self):
        cases = {
            "NVIDIA GeForce RTX 4070": ("nvidia", True),
            "AMD Radeon RX 7800 XT": ("amd", True),
            "AMD Radeon(TM) Graphics": ("amd", False),          # Ryzen built-in
            "Intel(R) Arc(TM) A770 Graphics": ("intel", True),
            "Intel(R) Arc(TM) Graphics": ("intel", False),       # Core Ultra built-in
            "Intel(R) UHD Graphics 750": ("intel", False),
            "Microsoft Basic Display Adapter": ("other", False),
        }
        for name, expected in cases.items():
            self.assertEqual(hw.classify_gpu(name), expected, name)


class TestRecommend(unittest.TestCase):
    def test_big_nvidia_card_gets_the_desktop_preset_at_full_precision(self):
        tier, settings, _ = hw.recommend(pc(("NVIDIA GeForce RTX 4070", 12.0)))
        self.assertEqual(tier, "nvidia-desktop")
        self.assertEqual(settings["WHISPER_MODEL_NAME"], "large-v3")
        self.assertEqual(settings["WHISPER_COMPUTE_TYPE"], "float16")

    def test_8gb_card_switches_to_int8_float16(self):
        _, settings, reasons = hw.recommend(pc(("NVIDIA GeForce RTX 3070", 8.0)))
        self.assertEqual(settings["WHISPER_COMPUTE_TYPE"], "int8_float16")
        self.assertTrue(reasons)

    def test_laptop_card_and_its_small_variant(self):
        tier, settings, _ = hw.recommend(pc(("NVIDIA GeForce RTX 3060 Laptop GPU", 6.0)))
        self.assertEqual((tier, settings["WHISPER_MODEL_NAME"]), ("nvidia-laptop", "medium"))
        _, settings, _ = hw.recommend(pc(("NVIDIA GeForce RTX 3050 Laptop GPU", 4.0)))
        self.assertEqual(settings["WHISPER_MODEL_NAME"], "small")

    def test_tiny_nvidia_card_falls_back_to_cpu(self):
        tier, _, reasons = hw.recommend(pc(("NVIDIA GeForce MX450", 2.0)))
        self.assertEqual(tier, "cpu-only")
        self.assertIn("too little", reasons[0])

    def test_built_in_graphics_only_is_cpu_only(self):
        tier, settings, _ = hw.recommend(pc(("Intel(R) Iris(R) Xe Graphics", 1.0), ram=16))
        self.assertEqual(tier, "cpu-only")
        self.assertEqual(settings["WHISPER_DEVICE"], "cpu")
        self.assertEqual(settings["READER_DEVICE"], "cpu")

    def test_8gb_ram_gets_the_lightest_models(self):
        _, settings, _ = hw.recommend(pc(("Intel(R) UHD Graphics", 0.5), ram=8))
        self.assertEqual(settings["WHISPER_MODEL_NAME"], "base")
        self.assertEqual(settings["OLLAMA_MODEL_NAME"], "gemma2:2b")

    def test_amd_card_runs_speech_on_the_cpu(self):
        tier, settings, _ = hw.recommend(pc(("AMD Radeon RX 7600", 8.0),
                                            ("AMD Radeon(TM) Graphics", 0.5)))
        self.assertEqual(tier, "amd-intel-gpu")
        self.assertEqual(settings["WHISPER_DEVICE"], "cpu")

    def test_nvidia_beats_built_in_graphics(self):
        tier, _, _ = hw.recommend(pc(("Intel(R) UHD Graphics 750", 2.0),
                                     ("NVIDIA GeForce RTX 4070", 12.0)))
        self.assertEqual(tier, "nvidia-desktop")

    def test_a_forced_tier_wins(self):
        tier, _, _ = hw.recommend(pc(("NVIDIA GeForce RTX 4070", 12.0)), tier="cpu-only")
        self.assertEqual(tier, "cpu-only")


class TestBuiltinAI(unittest.TestCase):
    """The built-in AI: the llama.cpp build follows the card, the model the memory."""

    E2B = "gemma-4-E2B_q4_0-it.gguf"

    def test_each_tier_gets_its_llama_build(self):
        cases = [
            (pc(("NVIDIA GeForce RTX 4070", 12.0)), "cuda"),
            (pc(("NVIDIA GeForce RTX 3060 Laptop GPU", 6.0)), "cuda"),
            (pc(("AMD Radeon RX 7600", 8.0)), "vulkan"),
            (pc(("Intel(R) UHD Graphics", 0.5)), "cpu"),
        ]
        for facts, variant in cases:
            tier, settings, _ = hw.recommend(facts)
            self.assertEqual(settings.get("AI_PROVIDER"), "builtin", tier)
            self.assertEqual(settings.get("LLAMA_VARIANT"), variant, tier)

    def test_a_small_laptop_card_gets_the_smaller_model(self):
        _, settings, reasons = hw.recommend(pc(("NVIDIA GeForce RTX 3050 Laptop GPU", 4.0)))
        self.assertEqual(settings.get("AI_BUILTIN_FILE"), self.E2B)
        self.assertTrue(any("E2B" in r for r in reasons))

    def test_8gb_of_ram_gets_the_smaller_model(self):
        _, settings, _ = hw.recommend(pc(("Intel(R) UHD Graphics", 0.5), ram=8))
        self.assertEqual(settings.get("AI_BUILTIN_FILE"), self.E2B)
        self.assertIn("E2B", settings.get("AI_BUILTIN_REPO", ""))

    def test_a_big_card_keeps_the_full_model(self):
        _, settings, _ = hw.recommend(pc(("NVIDIA GeForce RTX 4070", 12.0)))
        self.assertNotIn("AI_BUILTIN_FILE", settings)          # the engine's default: E4B

    def test_a_missing_runtime_is_reported_with_the_fix(self):
        settings = hw.load_preset("cpu-only")
        with mock.patch.object(hw, "installed_versions", return_value=dict.fromkeys(
                 ["faster-whisper", "kokoro", "torch", "nvidia-cublas-cu12"])), \
             mock.patch.object(hw, "_cached", return_value=True), \
             mock.patch.object(hw.os.path, "isfile", return_value=False):
            notes = hw.software_checks("cpu-only", settings)
        missing = [msg for ok, msg in notes if not ok and "get_llama" in msg]
        self.assertEqual(len(missing), 1, notes)

    def test_ollama_is_only_checked_when_it_is_the_provider(self):
        settings = dict(hw.load_preset("cpu-only"))
        with mock.patch.object(hw, "installed_versions", return_value=dict.fromkeys(
                 ["faster-whisper", "kokoro", "torch", "nvidia-cublas-cu12"])), \
             mock.patch.object(hw, "_cached", return_value=True), \
             mock.patch.object(hw, "_ollama_models", return_value=None) as ollama:
            hw.software_checks("cpu-only", settings)
            ollama.assert_not_called()
            settings["AI_PROVIDER"] = "ollama"
            notes = hw.software_checks("cpu-only", settings)
        ollama.assert_called_once()
        self.assertTrue(any("Ollama is not running" in msg for _, msg in notes))


class TestKeepChosenModel(unittest.TestCase):
    """--apply must not swap out an AI model the user picked for a preset's."""

    def test_the_users_model_wins(self):
        settings = {"OLLAMA_MODEL_NAME": "qwen2.5:7b"}
        note = hw.keep_chosen_model(settings, {"OLLAMA_MODEL_NAME": "gemma4-e4b:latest"})
        self.assertEqual(settings["OLLAMA_MODEL_NAME"], "gemma4-e4b:latest")
        self.assertIn("Keeping your own AI model", note)

    def test_the_users_ai_provider_wins(self):
        """Someone who switched to Ollama or Claude keeps it."""
        settings = {"AI_PROVIDER": "builtin", "OLLAMA_MODEL_NAME": "qwen2.5:7b"}
        note = hw.keep_chosen_model(settings, {"AI_PROVIDER": "claude"})
        self.assertEqual(settings["AI_PROVIDER"], "claude")
        self.assertIn("claude", note)

    def test_a_blank_choice_takes_the_preset(self):
        settings = {"OLLAMA_MODEL_NAME": "qwen2.5:7b"}
        self.assertIsNone(hw.keep_chosen_model(settings, {"OLLAMA_MODEL_NAME": ""}))
        self.assertEqual(settings["OLLAMA_MODEL_NAME"], "qwen2.5:7b")


class TestPresets(unittest.TestCase):
    def test_every_preset_uses_only_real_settings(self):
        """A typo in a preset would be silently ignored by the engine."""
        known = hw.parse_env(hw._read(os.path.join(REPO, ".env.example")))
        for tier in hw.TIERS:
            preset = hw.load_preset(tier)
            self.assertTrue(preset, tier)
            self.assertEqual(set(preset) - set(known), set(), tier)

    def test_every_preset_names_its_models(self):
        for tier in hw.TIERS:
            preset = hw.load_preset(tier)
            for key in ("WHISPER_MODEL_NAME", "OLLAMA_MODEL_NAME", "READER_DEVICE"):
                self.assertIn(key, preset, f"{tier} lacks {key}")


class TestMergeEnv(unittest.TestCase):
    def test_updates_in_place_and_keeps_comments(self):
        before = ('# header\nWHISPER_MODEL_NAME="large-v3"     # the model\n'
                  'HOTKEY_EN_RAW="f5"\n')
        after = hw.merge_env(before, {"WHISPER_MODEL_NAME": "small"})
        self.assertIn('WHISPER_MODEL_NAME="small"     # the model', after)
        self.assertIn('HOTKEY_EN_RAW="f5"', after)          # untouched
        self.assertTrue(after.startswith("# header"))

    def test_appends_settings_the_file_lacks(self):
        after = hw.merge_env('HOTKEY_EN_RAW="f5"\n', {"WHISPER_DEVICE": "cpu"})
        self.assertIn('WHISPER_DEVICE="cpu"', after)
        self.assertIn("check_hardware.py", after)

    def test_merged_values_parse_back(self):
        after = hw.merge_env('READER_DEVICE=auto # comment\n', {"READER_DEVICE": "cpu"})
        self.assertEqual(hw.parse_env(after)["READER_DEVICE"], "cpu")


class TestEnginePython(unittest.TestCase):
    def test_versions_come_from_the_engines_interpreter(self):
        """The checker usually runs under the system Python while the packages sit in
        venv/; it must ask that interpreter, not itself."""
        real = sys.executable
        with mock.patch.object(hw, "engine_python", return_value=real), \
             mock.patch.object(hw.sys, "executable", r"C:\elsewhere\python.exe"):
            found = hw.installed_versions(["pip", "surely-not-a-package"])
        self.assertTrue(found["pip"])                          # answered by the subprocess
        self.assertIsNone(found["surely-not-a-package"])


class TestWhisperDevice(unittest.TestCase):
    """WHISPER_DEVICE / WHISPER_COMPUTE_TYPE reach WhisperModel as documented."""

    def load(self, device, compute="float16", cuda_works=True):
        calls = []

        def fake_model(path, device, compute_type, **kw):
            calls.append((device, compute_type))
            if device == "cuda" and not cuda_works:
                raise RuntimeError("no CUDA")
            model = mock.Mock()
            model.transcribe.return_value = ([], None)
            return model
        with mock.patch.object(stt, "WHISPER_DEVICE", device), \
             mock.patch.object(stt, "WHISPER_COMPUTE_TYPE", compute), \
             mock.patch.object(stt, "resolve_whisper_model", return_value="/models/x"), \
             mock.patch.object(stt, "WhisperModel", side_effect=fake_model), \
             self.assertLogs(level="INFO"):             # keep these out of flow_debug.log
            stt.load_whisper_model()
        return calls, stt.model_runtime

    def test_auto_uses_the_gpu_at_the_chosen_precision(self):
        calls, runtime = self.load("auto", "int8_float16")
        self.assertEqual(calls, [("cuda", "int8_float16")])
        self.assertEqual(runtime, "GPU · int8_float16")

    def test_cpu_never_tries_the_gpu(self):
        calls, runtime = self.load("cpu")
        self.assertEqual(calls, [("cpu", "int8")])
        self.assertEqual(runtime, "CPU · int8")

    def test_a_failing_gpu_falls_back_to_cpu_int8(self):
        calls, runtime = self.load("auto", cuda_works=False)
        self.assertEqual(calls, [("cuda", "float16"), ("cpu", "int8")])
        self.assertEqual(runtime, "CPU · int8")


if __name__ == "__main__":
    unittest.main()
