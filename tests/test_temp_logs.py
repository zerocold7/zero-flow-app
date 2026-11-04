"""The temporary log folder of a test run or a tools/ check is gone when it ends.

Each run made one in the system's Temp folder and left it there: 826 had piled up.
The logs are still open when the process ends, and Windows will not delete an open
file, so the clean-up closes them first.
"""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN = """
import logging, sys
sys.path.insert(0, ROOT)
from zeroflow.paths import use_temporary_log_dir, log_dir
use_temporary_log_dir("zeroflow-cleanup-check-")
from zeroflow.logs import init_logging
init_logging("flow")                    # opens flow_debug.log and the crash log
logging.info("a line, so the file is written and open")
print(log_dir())
""".replace("ROOT", repr(ROOT))


class TestTemporaryLogFolder(unittest.TestCase):
    def run_once(self, env):
        out = subprocess.run([sys.executable, "-c", RUN], capture_output=True, text=True,
                             env=env, timeout=60, cwd=ROOT)
        self.assertEqual(out.returncode, 0, out.stderr[-800:])
        return out.stdout.strip().splitlines()[-1]

    def test_the_folder_is_removed_when_the_process_ends(self):
        env = {k: v for k, v in os.environ.items() if k != "ZEROFLOW_LOG_DIR"}
        folder = self.run_once(env)
        self.assertIn("zeroflow-cleanup-check-", folder)
        self.assertFalse(os.path.exists(folder), f"left behind: {folder}")

    def test_a_folder_chosen_by_the_caller_is_kept(self):
        mine = os.environ["ZEROFLOW_LOG_DIR"]           # this test run's own
        self.assertEqual(self.run_once(dict(os.environ)), mine)
        self.assertTrue(os.path.isdir(mine))


if __name__ == "__main__":
    unittest.main()
