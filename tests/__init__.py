"""Test-suite set-up, run before any test module is imported.

The tests crash readers and break microphones on purpose. Their logs go to a temporary
folder — passed on to the real Python processes some tests start — so they never land
in the program's own flow_debug.log and reader_debug.log, where they would read like
real faults. The folder is removed when the run ends.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow.paths import use_temporary_log_dir  # noqa: E402

use_temporary_log_dir("zeroflow-test-logs-")
