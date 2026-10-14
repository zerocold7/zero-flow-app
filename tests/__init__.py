"""Test-suite set-up, run before any test module is imported.

The tests crash readers and break microphones on purpose. Their logs go to a temporary
folder — passed on to the real Python processes some tests start — so they never land
in the program's own flow_debug.log and reader_debug.log, where they would read like
real faults.
"""
import os
import tempfile

os.environ.setdefault("ZEROFLOW_LOG_DIR", tempfile.mkdtemp(prefix="zeroflow-test-logs-"))
