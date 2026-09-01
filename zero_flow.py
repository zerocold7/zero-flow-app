"""
Zero- Flow Engine — the whole engine in one window.

    F5-F10 / Shift+F1-F3   dictate, translate, fix a line   (speech -> text)
    F4                     read the highlighted text aloud   (text -> speech)
    Esc                    cancel a recording / silence the reader

This process runs the dictation half itself and launches the reader as a **child
process**. The child is started without CREATE_NEW_CONSOLE, so Windows hands it this
process's console: its output appears in this window, and the pair looks like a single
program. The child owns the one tray icon, because every control in that menu toggles
state that lives inside the reader.

--------------------------------------------------------------------------------
WHY A CHILD PROCESS AND NOT A THREAD
--------------------------------------------------------------------------------
An earlier version really did host both halves in one process. It worked, but it had
to force the voice model onto the CPU: torch 2.5.1+cu121 bundles cuDNN 9.1 while
CTranslate2 (Whisper) needs the pip-installed cuDNN 9.23, Windows loads exactly one
DLL per base name per process, and whichever initialises CUDA second gets the wrong
one and **segfaults** — in either load order, with no exception to catch. That cost
about 2 seconds of silence before the first spoken word.

Separate processes have separate DLL namespaces, so the conflict simply does not
arise: Whisper keeps the GPU here, Kokoro gets the GPU over there, and time to first
word drops to ~0.2 s. A crash in either half also stops being fatal to the other.

The two coordinate over named Windows objects in `flow_signals.py` — the microphone
interlock and the clipboard mutex both work across the process boundary.

Both halves still run standalone: `local_flow.py` and `python -m reader`.
"""
import logging
import os
import subprocess
import sys
import threading
import traceback

import keyboard

try:
    # local_flow FIRST, and this order is load-bearing: it pulls in faster-whisper,
    # which must claim the CUDA DLLs before any WinRT library (win11toast, reached
    # through engine_ui) can be loaded. Get this backwards and CTranslate2 segfaults
    # the process when it loads the model. Importing it first also establishes
    # "flow_debug.log" as this process's log.
    import local_flow
    import flow_core
    import flow_signals as signals
    import engine_ui as ui
except ImportError as e:
    print(f"❌ Critical error: Missing local module: {e}")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
reader_process = None


def spawn_reader():
    """Launch the reader as a child sharing this console window.

    No `creationflags`: that is the entire trick. CREATE_NEW_CONSOLE would give it a
    second window, CREATE_NO_WINDOW would swallow its output; inheriting ours is what
    makes two processes look like one program.
    """
    env = dict(os.environ, ZEROFLOW_CHILD="1")
    try:
        return subprocess.Popen([sys.executable, "-m", "reader"], cwd=BASE_DIR, env=env)
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
    """If the child dies on its own, say so loudly — the vanished tray icon is
    otherwise the only clue, and dictation carries on working regardless."""
    if reader_process is None:
        return
    code = reader_process.wait()
    if code == 0:
        return                                   # a clean exit is handled by watch_for_exit
    logging.error(f"The reader half exited unexpectedly (code {code}).")
    print(f"\n{ui.C_ERR}[engine]{ui.C_RESET} The reader half stopped (exit code {code}). "
          f"Dictation is unaffected; restart the engine to get F4 back.")


def shutdown():
    """Stop the child, then this process."""
    if reader_process and reader_process.poll() is None:
        try:
            reader_process.terminate()
            reader_process.wait(timeout=5)
        except Exception:
            try:
                reader_process.kill()
            except Exception:
                pass
    os._exit(0)


def print_boot_sequence(llm_model):
    os.system('cls' if os.name == 'nt' else 'clear')
    hk = local_flow.HOTKEYS
    read_key = os.getenv("HOTKEY_READ", "f4").upper()
    lines = [
        f"{ui.C_ACCENT}┌────────────────────────────────────────────────────────┐{ui.C_RESET}",
        f"{ui.C_ACCENT}│ {ui.Fore.MAGENTA}       Z E R O -   F L O W   E N G I N E             {ui.C_ACCENT}│{ui.C_RESET}",
        f"{ui.C_ACCENT}│ {ui.C_RESET}🔗 Speech to text: {ui.C_GOOD}[Whisper]{ui.C_ACCENT}                           │{ui.C_RESET}",
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


def main():
    global reader_process
    logging.info("=== Zero- Engine Boot Sequence Initiated ===")

    local_flow.boot()                            # loads Whisper on the GPU
    print_boot_sequence(local_flow.get_ollama_model())
    ui.set_window_icon()
    ui.show_toast("🚀 Zero- Flow Engine Online",
                  "Dictation and read-aloud are both active.", flow_core.ENABLE_TOASTS)

    # Started after Whisper is up, so the child's torch import cannot race our CUDA
    # load and its "ready" line lands under the banner rather than through it.
    reader_process = spawn_reader()
    threading.Thread(target=watch_for_exit, daemon=True).start()
    threading.Thread(target=watch_reader, daemon=True).start()

    local_flow.register_hotkeys()
    keyboard.wait()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        shutdown()
    except Exception:
        logging.critical(f"Fatal engine crash: {traceback.format_exc()}")
        shutdown()
