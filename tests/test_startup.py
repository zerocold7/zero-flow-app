"""Start-up cost — what importing the dictation half drags in.

CTranslate2 (faster-whisper's engine) imports torch and transformers for its model
converters, which this engine never uses: about 6 s on every start, and in every test
run that imports local_flow. local_flow skips them for that one import. These tests
fail if the skip stops working (say, after a CTranslate2 upgrade) or if it leaves the
modules unimportable for code that genuinely needs them.
"""
import importlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import local_flow  # noqa: F401  — the import under test


class TestConverterImportsSkipped(unittest.TestCase):
    def converters(self):
        module = sys.modules.get("ctranslate2.converters.transformers")
        if module is None:
            self.skipTest("CTranslate2 no longer has this converter module")
        return module

    def test_ctranslate2_did_not_import_torch(self):
        """Read from CTranslate2's own module, so it holds whatever else the test run
        has imported since."""
        self.assertFalse(hasattr(self.converters(), "torch"),
                         "CTranslate2 imported torch while local_flow loaded — ~6 s per start")

    def test_ctranslate2_did_not_import_transformers(self):
        self.assertFalse(hasattr(self.converters(), "transformers"))

    def test_no_placeholders_left_behind(self):
        """The skip marks the modules as missing only during the import. A leftover
        marker would make every later `import torch` fail in this process."""
        for name in ("torch", "transformers"):
            self.assertIsNot(sys.modules.get(name, "not imported"), None, name)

    def test_whisper_itself_loaded(self):
        faster_whisper = importlib.import_module("faster_whisper")
        self.assertTrue(hasattr(faster_whisper, "WhisperModel"))


if __name__ == "__main__":
    unittest.main()
