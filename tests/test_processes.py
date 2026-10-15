"""The engine's processes: one copy at a time, the reader supervised, nothing left
behind.

  * Two engines both answered every hotkey: every dictation was pasted twice.
  * A crash of the engine's main process left the reader running on its own.
  * A crash of the reader exited with code 0, which the supervisor took for a clean
    exit — F4 died silently and was never brought back.
  * "Exit Reader" on a standalone reader also shut down a running full engine.

Some of these start real Python processes, because what is being tested is how
Windows treats them.
"""
import ctypes
import os
import subprocess
import sys
import textwrap
import unittest
import uuid
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from zeroflow import engine
from zeroflow import logs
from zeroflow import paths
from zeroflow import signals as flow_signals
from zeroflow import supervisor

from reader import app as reader_app

SYNCHRONIZE = 0x00100000


def process_is_gone(pid, timeout_ms):
    """True once process `pid` has exited (or never existed)."""
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = ctypes.c_void_p
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return True
    try:
        return kernel32.WaitForSingleObject(ctypes.c_void_p(handle), timeout_ms) == 0
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))


def run_python(code):
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code)], cwd=ROOT,
                          capture_output=True, text=True, timeout=60)


class TestSingleInstance(unittest.TestCase):
    def test_a_second_claim_is_refused(self):
        role = f"test-{uuid.uuid4()}"
        self.assertTrue(flow_signals.claim_single_instance(role))
        self.assertFalse(flow_signals.claim_single_instance(role))

    def test_another_process_is_refused_while_this_one_holds_it(self):
        role = f"test-{uuid.uuid4()}"
        self.assertTrue(flow_signals.claim_single_instance(role))
        other = run_python(f"""
            from zeroflow import signals as flow_signals
            print(flow_signals.claim_single_instance({role!r}))
        """)
        self.assertEqual(other.stdout.strip(), "False", other.stderr)


class TestSecondCopyStopsAtTheDoor(unittest.TestCase):
    """Each way of starting the engine checks the claim before loading anything."""

    def refused(self, module, start, boot_name):
        # If the check is missing, the first loading step stops the test right there —
        # rather than starting a real engine that waits on the keyboard forever.
        loading = AssertionError("started loading although another copy is running")
        with mock.patch.object(module.signals, "claim_single_instance", return_value=False), \
             mock.patch.object(module.ui, "already_running") as told, \
             mock.patch.object(*boot_name, side_effect=loading):
            start()
        told.assert_called_once()

    def test_the_whole_engine(self):
        self.refused(supervisor, supervisor.main, (engine, "boot"))

    def test_the_dictation_half_alone(self):
        self.refused(engine, engine.main, (engine, "boot"))

    def test_the_reader_alone(self):
        with mock.patch.object(reader_app, "CHILD_MODE", False):
            self.refused(reader_app, reader_app.main, (reader_app, "register_hotkeys"))

    def test_the_engines_own_reader_does_not_claim(self):
        """The engine holds the reader's claim; its child must not be turned away."""
        with mock.patch.object(reader_app, "CHILD_MODE", True), \
             mock.patch.object(reader_app.signals, "claim_single_instance",
                               return_value=False) as claim, \
             mock.patch.object(reader_app, "register_hotkeys"), \
             mock.patch.object(reader_app.keyboard, "wait"), \
             mock.patch.object(reader_app.pystray, "Icon"), \
             mock.patch("builtins.print"):
            reader_app.main()
        claim.assert_not_called()


class TestChildDiesWithParent(unittest.TestCase):
    def test_a_bound_child_is_killed_when_its_parent_crashes(self):
        """The parent here dies the hard way (no clean-up code runs), like a native
        crash or Task Manager's End task."""
        parent = run_python("""
            import os, subprocess, sys
            from zeroflow import signals as flow_signals
            # No inherited output: an orphaned child would hold the test's pipe open.
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
            flow_signals.bind_child_to_this_process(child)
            print(child.pid, flush=True)
            os._exit(3)
        """)
        child_pid = int(parent.stdout.strip())
        self.assertTrue(process_is_gone(child_pid, 5000), "the child outlived its parent")


class TestReaderExitCode(unittest.TestCase):
    def test_a_crash_exits_with_an_error_code(self):
        """Code 0 told the supervisor all was well."""
        crashed = run_python("""
            import runpy
            from reader import app
            def broken():
                raise RuntimeError("voice model failed")
            app.main = broken
            runpy.run_module("reader", run_name="__main__")
        """)
        self.assertNotEqual(crashed.returncode, 0, crashed.stderr)


class TestTestsLeaveTheLogsAlone(unittest.TestCase):
    def test_the_suite_logs_outside_the_program_folder(self):
        """The tests' deliberate crashes and broken microphones used to land in the
        real flow_debug.log and reader_debug.log, where they read like real faults."""
        opened = [logs._handler.baseFilename] if logs._handler else []
        for path in opened + [paths.log_path("flow"), paths.log_path("reader")]:
            self.assertNotEqual(
                os.path.dirname(os.path.abspath(path)), ROOT,
                f"{path} is the program's own log. Run the tests from the project folder "
                f"with:  python -m unittest discover -s tests -t .")


class TestCrashLogging(unittest.TestCase):
    """A crash used to leave nothing in the logs — invisible under the silent launcher."""

    def crash(self, component, code):
        files = [os.path.join(paths.log_dir(), f"{component}_{kind}.log")
                 for kind in ("debug", "crash")]
        for path in files:
            self.addCleanup(lambda p=path: os.path.exists(p) and os.unlink(p))
        run_python(f"from zeroflow import logs\nlogs.init_logging({component!r})\n{code}")
        found = {}
        for path in files:
            if os.path.exists(path):
                with open(path, encoding="utf-8", errors="replace") as f:
                    found[os.path.basename(path)] = f.read()
        return found

    def test_a_native_crash_is_written_to_the_crash_log(self):
        """A segfault skips all of Python's error handling."""
        logs = self.crash("crashtest_native", "import ctypes\nctypes.string_at(0)")
        self.assertIn("Windows fatal exception", logs.get("crashtest_native_crash.log", ""))

    def test_an_uncaught_error_on_a_thread_is_logged(self):
        logs = self.crash("crashtest_thread",
                          "import threading\nt = threading.Thread(target=lambda: 1 / 0)\n"
                          "t.start()\nt.join()")
        debug = logs.get("crashtest_thread_debug.log", "")
        self.assertIn("CRITICAL", debug)
        self.assertIn("ZeroDivisionError", debug)


class FakeReader:
    def __init__(self, code):
        self.code = code

    def wait(self):
        return self.code

    def poll(self):
        return self.code


class TestReaderSupervision(unittest.TestCase):
    def supervise(self, first_code, later_codes, exit_requested=False):
        """Run watch_reader with a reader that exits with `first_code`, and restarts
        that exit with `later_codes` in turn. Returns how many restarts were made."""
        spawned = [FakeReader(code) for code in later_codes]
        spawn = mock.Mock(side_effect=lambda: spawned.pop(0) if spawned else None)
        with mock.patch.object(supervisor, "reader_process", FakeReader(first_code)), \
             mock.patch.object(supervisor, "spawn_reader", spawn), \
             mock.patch.object(supervisor.time, "sleep"), \
             mock.patch.object(supervisor.signals, "exit_requested",
                               return_value=exit_requested, create=True), \
             mock.patch("builtins.print"), \
             mock.patch.object(supervisor, "logging"):
            supervisor.watch_reader()
        return spawn.call_count

    def test_a_crashed_reader_is_restarted(self):
        restarts = self.supervise(1, [supervisor.STATUS_CONTROL_C_EXIT])
        self.assertEqual(restarts, 1)

    def test_it_gives_up_after_repeated_crashes(self):
        """A reader that can never start must not be restarted forever."""
        restarts = self.supervise(1, [1] * 10)
        self.assertEqual(restarts, supervisor.MAX_READER_RESTARTS)

    def test_exit_from_the_tray_is_not_a_crash(self):
        self.assertEqual(self.supervise(0, [1], exit_requested=True), 0)

    def test_closing_the_console_is_not_a_crash(self):
        self.assertEqual(self.supervise(supervisor.STATUS_CONTROL_C_EXIT, [1]), 0)

    def test_the_engine_stopping_the_reader_is_not_a_crash(self):
        """shutdown() ends the reader first; that exit is not one to restart (or to
        log as "exited unexpectedly" on the way out)."""
        with mock.patch.object(supervisor, "shutting_down", True, create=True):
            self.assertEqual(self.supervise(1, [1]), 0)


class TestReaderExitButton(unittest.TestCase):
    def press_exit(self, child_mode):
        with mock.patch.object(reader_app, "CHILD_MODE", child_mode), \
             mock.patch.object(reader_app.voice_engine, "interrupt_audio"), \
             mock.patch.object(reader_app.signals, "request_exit") as request_exit, \
             mock.patch.object(reader_app.os, "_exit"):
            reader_app.exit_application(mock.Mock(), None)
        return request_exit.called

    def test_a_standalone_reader_does_not_shut_down_the_engine(self):
        self.assertFalse(self.press_exit(child_mode=False))

    def test_the_engines_reader_shuts_the_whole_engine_down(self):
        self.assertTrue(self.press_exit(child_mode=True))


if __name__ == "__main__":
    unittest.main()
