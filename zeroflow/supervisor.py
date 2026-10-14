"""
The whole engine in one window: dictation in this process, the reader as a child.

    F5-F10 / Shift+F1-F3   dictate, translate, fix a line   (speech -> text)
    F4                     read the highlighted text aloud   (text -> speech)
    Esc                    cancel a recording / silence the reader

Why a child process and not a thread — and how the two coordinate — is explained in
zero_flow.py's docstring and ARCHITECTURE.md.
"""
import logging
import os
import subprocess
import sys
import threading
import time

import keyboard

# engine FIRST, and this order is load-bearing: it pulls in faster-whisper, which
# must claim the CUDA DLLs before any WinRT library (win11toast, reached through ui)
# can be loaded. Get this backwards and CTranslate2 segfaults the process when it
# loads the model. Importing it first also establishes "flow_debug.log" as this
# process's log.
from zeroflow import engine
from zeroflow import settings, signals, stt, ui
from zeroflow.paths import BASE_DIR


# What the reader exits with when the shared console window is closed or gets Ctrl+C:
# the user stopping the engine, not a crash.
STATUS_CONTROL_C_EXIT = 0xC000013A


# The reader is restarted if it crashes, but not forever (see watch_reader).
MAX_READER_RESTARTS = 3
READER_STABLE_SECONDS = 60
reader_process = None
shutting_down = False     # set by shutdown(), which stops the reader itself


def spawn_reader():
    """Launch the reader as a child sharing this console window.

    No `creationflags`: that is the entire trick. CREATE_NEW_CONSOLE would give it a
    second window, CREATE_NO_WINDOW would swallow its output; inheriting ours is what
    makes two processes look like one program.
    """
    env = dict(os.environ, ZEROFLOW_CHILD="1")
    try:
        child = subprocess.Popen([sys.executable, "-m", "reader"], cwd=BASE_DIR, env=env)
        # So a crash of this process — no clean-up code runs — cannot leave the
        # reader running on its own with an "Exit Engine" that exits nothing.
        signals.bind_child_to_this_process(child)
        return child
    except Exception as e:
        logging.error(f"Could not start the reader half: {e}")
        print(f"{ui.C_ERR}[engine]{ui.C_RESET} Reader failed to start: {e}")
        print(f"{ui.C_ERR}[engine]{ui.C_RESET} Dictation still works; F4 will not.")
        return None


def watch_for_exit():
    """The tray icon belongs to the child, so "Exit Engine" reaches us as a signal."""
    if not signals.available():
        return
    if signals.wait_for_exit():
        logging.info("Exit requested from the tray; shutting the engine down.")
        shutdown()


def watch_reader():
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
        if shutting_down or signals.exit_requested():
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


def shutdown(code=0):
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


def print_boot_sequence(llm_model):
    os.system('cls' if os.name == 'nt' else 'clear')
    hk = settings.HOTKEYS
    read_key = os.getenv("HOTKEY_READ", "f4").upper()
    lines = [
        f"{ui.C_ACCENT}┌────────────────────────────────────────────────────────┐{ui.C_RESET}",
        f"{ui.C_ACCENT}│ {ui.Fore.MAGENTA}       Z E R O -   F L O W   E N G I N E             {ui.C_ACCENT}│{ui.C_RESET}",
        f"{ui.C_ACCENT}│ {ui.C_RESET}🔗 Speech to text: {ui.C_GOOD}[Whisper {settings.WHISPER_MODEL_NAME} · "
        f"{stt.model_runtime}]{ui.C_RESET}",
        f"{ui.C_ACCENT}│ {ui.C_RESET}🔗 Text to speech: {ui.C_GOOD}[Kokoro-82M]{ui.C_ACCENT}                        │{ui.C_RESET}",
        f"{ui.C_ACCENT}│ {ui.C_RESET}🔗 Neural pipeline: {ui.C_GOOD}[{llm_model}]{ui.C_RESET}",
        f"{ui.C_ACCENT}└────────────────────────────────────────────────────────┘{ui.C_RESET}",
        f"  {ui.C_ACCENT}DICTATE{ui.C_RESET}   (the key forces the language)",
        f"   {ui.C_ACCENT}'{hk['en_raw'].upper()}'{ui.C_RESET} English · raw      {ui.C_GOOD}'{hk['en_polish'].upper()}'{ui.C_RESET} English · polish",
        f"   {ui.C_WARN}'{hk['ar_raw'].upper()}'{ui.C_RESET} Arabic · raw       {ui.C_WARN}'{hk['ar_polish'].upper()}'{ui.C_RESET} Arabic · polish",
        f"  {ui.C_ACCENT}TRANSLATE{ui.C_RESET}",
        f"   {ui.Fore.MAGENTA}'{hk['en2ar'].upper()}'{ui.C_RESET} English → Arabic   {ui.Fore.MAGENTA}'{hk['ar2en'].upper()}'{ui.C_RESET} Arabic → English",
        f"  {ui.C_ACCENT}READ ALOUD{ui.C_RESET}",
        f"   {ui.C_GOOD}'{read_key}'{ui.C_RESET} speak the highlighted text  (voice + options in the tray)",
        f"  {ui.C_ACCENT}ACTIONS{ui.C_RESET}",
        f"   {ui.C_GOOD}'{hk['fix'].upper()}'{ui.C_RESET} fix line   {ui.Fore.MAGENTA}'{hk['maintenance'].upper()}'{ui.C_RESET} vocab cleanup   "
        f"{ui.C_GOOD}'{hk['purge'].upper()}'{ui.C_RESET} clear logs   {ui.C_ERR}'{hk['panic'].upper()}'{ui.C_RESET} cancel / silence",
        f"{ui.C_ACCENT}========================================================={ui.C_RESET}\n",
    ]
    for line in lines:
        print(line)


def run():
    """Run the whole engine (zero_flow.py); exit code 1 after a crash."""
    try:
        main()
    except KeyboardInterrupt:
        shutdown()
    except Exception:
        engine.report_fatal_error("engine")
        shutdown(1)


def main():
    global reader_process
    logging.info("=== Zero- Engine Boot Sequence Initiated ===")
    # The whole engine claims both roles, so neither a second engine nor a standalone
    # half (Launch_Flow / Launch_Reader) can run beside it and double every action.
    if not (signals.claim_single_instance("dictation")
            and signals.claim_single_instance("reader")):
        ui.already_running()
        return

    engine.boot()                                # loads Whisper on the GPU
    print_boot_sequence(engine.get_ollama_model())
    ui.set_window_icon()
    ui.show_toast("🚀 Zero- Flow Engine Online",
                  "Dictation and read-aloud are both active.", settings.ENABLE_TOASTS)

    # Started after Whisper is up, so the child's torch import cannot race our CUDA
    # load and its "ready" line lands under the banner rather than through it.
    reader_process = spawn_reader()
    threading.Thread(target=watch_for_exit, daemon=True).start()
    threading.Thread(target=watch_reader, daemon=True).start()

    engine.register_hotkeys()
    keyboard.wait()
