"""Test-suite set-up, run before any test module is imported.

The tests crash readers and break microphones on purpose. Their logs go to a temporary
folder — passed on to the real Python processes some tests start — so they never land
in the real logs, where they would read like real faults. The folder is removed when
the run ends.

The settings come from a temporary settings file too, holding only the models folder in
use now: every other setting is at its default, so this PC's own settings cannot hide or
cause a failure, and no test ever migrates or writes into the real %APPDATA%. It is set
before zeroflow.paths is imported, which places the vocabulary and history beside it.
"""
import atexit
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if not os.getenv("ZEROFLOW_SETTINGS"):
    _folder = tempfile.mkdtemp(prefix="zeroflow-test-settings-")
    _models = os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
    with open(os.path.join(_folder, "settings.json"), "w", encoding="utf-8") as _f:
        json.dump({"MODELS_DIR": _models}, _f)
    os.environ["ZEROFLOW_SETTINGS"] = os.path.join(_folder, "settings.json")
    atexit.register(shutil.rmtree, _folder, True)

from zeroflow.paths import use_temporary_log_dir  # noqa: E402

use_temporary_log_dir("zeroflow-test-logs-")
