"""
The whole Engine (zero_flow.py): Dictation and the Qt interface in this process, the
Reader as a child. Why a child process and not a thread: ARCHITECTURE.md §1 and §12.
The interface (tray, overlay, Settings window) is zeroflow/app.py.
"""
import logging
import os
import subprocess
import sys
import threading
import time

# engine FIRST, and this order is load-bearing: it pulls in faster-whisper, which
# must claim the CUDA DLLs before any WinRT library (win11toast, reached through ui)
# can be loaded. Get this backwards and CTranslate2 segfaults the process when it
# loads the model. Importing it first also establishes "flow_debug.log" as this
# process's log.
from zeroflow import engine
from zeroflow import frozen, settings, signals, stt, ui
from zeroflow.paths import BASE_DIR


# What the reader exits with when the shared console window is closed or gets Ctrl+C:
# the user stopping the engine, not a crash.
STATUS_CONTROL_C_EXIT = 0xC000013A


# The reader is restarted if it crashes, but not forever (see watch_reader).
MAX_READER_RESTARTS = 3
READER_STABLE_SECONDS = 60
RESTART_FLAG = "--restart"
RESTART_WAIT = 10.0      # seconds a restarted Engine waits for the old one's claim
DETACHED = 0x00000008    # DETACHED_PROCESS: the new Engine outlives this one
reader_process = None
reader_wanted = True     # False once "Reader on" has been switched off
shutting_down = False     # set by shutdown(), which stops the reader itself


def spawn_reader() -> subprocess.Popen | None:
    """Launch the Reader as a child process: a Qt-free process of its own, so it can hold
    CUDA freely, and one that ends with this process (signals.bind_child_to_this_process)."""
    try:
        child = subprocess.Popen(frozen.child_command("reader"), cwd=BASE_DIR)
        # So a crash of this process — no clean-up code runs — cannot leave the
        # Reader running on its own.
        signals.bind_child_to_this_process(child)
        return child
    except Exception as e:
        logging.error(f"Could not start the reader half: {e}")
        print(f"{ui.C_ERR}[engine]{ui.C_RESET} Reader failed to start: {e}")
        return None


def watch_for_exit() -> None:
    """The tray icon belongs to the child, so "Exit Engine" reaches us as a signal."""
    if not signals.available():
        return
    if signals.wait_for_exit():
        logging.info("Exit requested from the tray; shutting the engine down.")
        shutdown()


def watch_reader() -> None:
    """Restart the reader if it dies on its own, and say so — the vanished tray icon
    is otherwise the only clue, since dictation carries on regardless.

    Restarts wait 2, 4, then 8 s, and stop after MAX_READER_RESTARTS in a row: a
    reader that cannot start at all (a broken voice model, say) must not loop
    forever. One that ran for READER_STABLE_SECONDS earns a fresh set of tries."""
    global reader_process
    restarts = 0
    while reader_process is not None:
        started = time.monotonic()
        code = reader_process.wait()
        if shutting_down or not reader_wanted or signals.exit_requested():
            return                               # the engine is closing it on purpose
        if code == STATUS_CONTROL_C_EXIT:
            logging.info("The reader half stopped with the console (window closed or Ctrl+C).")
            return
        if time.monotonic() - started > READER_STABLE_SECONDS:
            restarts = 0
        if restarts >= MAX_READER_RESTARTS:
            logging.error(f"The reader half keeps stopping (exit code {code}); giving up.")
            print(f"\n{ui.C_ERR}[engine]{ui.C_RESET} The reader keeps stopping (exit code "
                  f"{code}) — F4 is off. Dictation is unaffected; details in reader_debug.log.")
            return
        restarts += 1
        delay = 2 ** restarts
        logging.error(f"The reader half exited unexpectedly (code {code}); restarting in "
                      f"{delay} s ({restarts}/{MAX_READER_RESTARTS}).")
        print(f"\n{ui.C_WARN}[engine]{ui.C_RESET} The reader stopped (exit code {code}); "
              f"restarting it in {delay} s.")
        time.sleep(delay)
        reader_process = spawn_reader()


def shutdown(code: int = 0) -> None:
    """Stop the child, then this process (exit code `code`: non-zero after a crash,
    so the launcher can tell)."""
    global shutting_down
    shutting_down = True
    if reader_process and reader_process.poll() is None:
        try:
            reader_process.terminate()
            reader_process.wait(timeout=5)
        except Exception:
            try:
                reader_process.kill()
            except Exception:
                pass
    os._exit(code)


def show_banner() -> None:
    """The banner of the whole Engine, for the developer launcher that has a console."""
    sections = engine.key_sections(panic="cancel / silence")
    sections.insert(2, ("READ ALOUD", None, [
        [(settings.HOTKEY_READ, "speak the highlighted text", ui.C_GOOD)]]))
    ui.print_banner("Z E R O -   F L O W   E N G I N E",
                    [("Speech to text", f"Whisper {settings.WHISPER_MODEL_NAME} · {stt.model_runtime}"),
                     ("Text to speech", "Kokoro-82M"),
                     ("AI model", engine.model_name())],
                    sections)


class DictationHalf:
    """Dictation as `zeroflow.halves.Halves` drives it: on holds the speech model, the
    AI and the keys; off holds none of them."""
    running = False

    def start(self) -> None:
        engine.load_models()
        engine.register_hotkeys()
        self.running = True

    def stop(self) -> None:
        self.running = False
        engine.unregister_hotkeys()
        engine.free_models()


class ReaderHalf:
    """The Reader as `Halves` drives it: on is the child process, off ends it (and its
    voice model's memory)."""

    @property
    def running(self) -> bool:
        return reader_process is not None and reader_process.poll() is None

    def start(self) -> None:
        global reader_process, reader_wanted
        reader_wanted = True
        reader_process = spawn_reader()
        if reader_process is None:
            raise RuntimeError("the Reader process did not start")
        threading.Thread(target=watch_reader, daemon=True).start()

    def stop(self) -> None:
        global reader_wanted
        reader_wanted = False
        process = reader_process
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception:
                process.kill()


def restart() -> None:
    """Saving settings: start a new Engine, which waits for this one's claim on the single
    copy (up to RESTART_WAIT seconds), then end this one."""
    try:
        subprocess.Popen(frozen.engine_command(RESTART_FLAG),
                         cwd=BASE_DIR, creationflags=DETACHED)
    except Exception:
        logging.error("Could not start the new Engine; staying as it is.", exc_info=True)
        return
    logging.info("Restarting: the new Engine has been started.")
    shutdown()


def run() -> None:
    """Run the whole Engine (zero_flow.py); exit code 1 after a crash."""
    try:
        main()
    except KeyboardInterrupt:
        shutdown()
    except Exception:
        engine.report_fatal_error("engine")
        shutdown(1)


def main() -> None:
    global reader_process
    restarting = RESTART_FLAG in sys.argv
    logging.info(f"=== Zero- Engine Boot Sequence Initiated (restart={restarting}) ===")
    # The whole Engine claims both roles, so a second one cannot run beside it and double
    # every action. A restarted Engine waits for the one that started it to let go.
    wait = RESTART_WAIT if restarting else 0
    if not (signals.claim_single_instance("dictation", wait)
            and signals.claim_single_instance("reader", wait)):
        ui.already_running()
        return

    # Qt comes after the speech library: it must claim the CUDA DLLs first (see the top).
    threading.Thread(target=watch_for_exit, daemon=True).start()   # a request to quit, from outside
    from zeroflow import app
    app.run(DictationHalf(), ReaderHalf(), restart_engine=restart, quit_engine=shutdown,
            banner=show_banner)
