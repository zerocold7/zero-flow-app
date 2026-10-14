"""flow_history.md — every dictation, kept to a fixed size.

The size cap used to be checked only at start-up, so an engine left running for days
grew the file without limit, and the trim cut wherever the byte count fell — often
through the middle of an entry, or of an Arabic letter.
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import local_flow

CAP = 2_000


class HistoryTestCase(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".md")
        os.close(handle)
        self.addCleanup(os.unlink, self.path)
        for patcher in (mock.patch.object(local_flow, "HISTORY_FILE", self.path),
                        mock.patch.object(local_flow, "HISTORY_MAX_BYTES", CAP)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def read(self):
        with open(self.path, encoding="utf-8") as f:     # raises if a letter was cut
            return f.read()

    def dictate(self, count, text="مرحبا، هذه جملة تجريبية طويلة بعض الشيء"):
        for i in range(count):
            local_flow.log_to_history(f"{i}: {text}", "ar_raw")


class TestHistoryCap(HistoryTestCase):
    def test_the_cap_holds_while_the_engine_runs(self):
        """Checked on every write, not only at start-up."""
        self.dictate(100)
        self.assertLessEqual(os.path.getsize(self.path), CAP)

    def test_the_newest_dictation_is_kept(self):
        self.dictate(100)
        self.assertIn("99: مرحبا", self.read())

    def test_trimming_keeps_whole_entries(self):
        """After the trim notice, the file starts at an entry's header."""
        self.dictate(100)
        text = self.read()
        self.assertTrue("...]\n\n" in text, "the file was never trimmed")
        body = text.split("...]\n\n", 1)[1]
        self.assertRegex(body, r"^\[\d\d:\d\d:\d\d\] \[AR_RAW\]\n\d+: ")

    def test_a_small_file_is_left_alone(self):
        self.dictate(2)
        self.assertNotIn("trimmed", self.read())


if __name__ == "__main__":
    unittest.main()
