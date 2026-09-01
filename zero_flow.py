"""
Zero- Flow Engine — both halves in one process, one console, one tray icon.

    F5-F10 / Shift+F1-F3   dictate, translate, fix a line   (speech -> text)
    F4                     read the highlighted text aloud   (text -> speech)
    Esc                    cancel a recording / silence the reader

This is the merged engine. The two halves still exist as standalone programs —
`local_flow.py` and `python -m reader` — and nothing here changes how they behave;
it just hosts them together so there is one window to look at.

--------------------------------------------------------------------------------
THE ONE HARD RULE: Kokoro runs on the CPU in this process.
--------------------------------------------------------------------------------
torch 2.5.1+cu121 bundles cuDNN 9.1. CTranslate2 (Whisper) needs the pip-installed
cuDNN 9.23. Windows loads exactly one DLL per base name per process, so whichever
CUDA library loads second gets the wrong one and the process dies — a hard segfault
in either load order, not an exception anything can catch. Whisper keeps the GPU
because that is where the seconds are.

The cost is real but bounded: measured time-to-first-word for a paragraph is ~2.0 s
on CPU against ~0.2 s on GPU. Sentence batching and a background preload get it
there; run the halves as two processes (Launch_All.bat) if you want the 0.2 s.

`voice_engine.force_cpu()` enforces this and overrides `READER_DEVICE` on purpose.
Do not remove it without re-testing both models on CUDA in one process.
"""
import logging
import os
import sys
import threading
import traceback

import keyboard
import pystray
from pystray import MenuItem

try:
    # local_flow FIRST, and this order is load-bearing: it pulls in faster-whisper,
    # which must claim the CUDA DLLs before any WinRT library (win11toast, reached
    # through engine_ui) can be loaded. Get this backwards and CTranslate2 segfaults
    # the process when it loads the model. Importing it first also establishes
    # "flow_debug.log" as this process's single log, before the reader asks for one.
    import local_flow
    import flow_core
    import engine_ui as ui
    from reader import app as reader_app
    from reader import voice_engine
except ImportError as e:
    print(f"❌ Critical error: Missing local module: {e}")
    sys.exit(1)

CUDA_CONFLICT_REASON = ("Whisper holds the GPU in the merged engine; torch and "
                        "CTranslate2 cannot both load CUDA in one process")


def build_tray_menu():
    """One icon for the whole engine: the reader's controls plus a single exit."""
    return pystray.Menu(
        *reader_app.tray_items(),
        pystray.Menu.SEPARATOR,
        MenuItem("Exit Engine", lambda icon, item: (voice_engine.interrupt_audio(),
                                                    icon.stop(), os._exit(0))),
    )


def print_boot_sequence(llm_model):
    os.system('cls' if os.name == 'nt' else 'clear')
    hk = local_flow.HOTKEYS
    read_key = reader_app.HOTKEY_READ.upper()
    lines = [
        f"{ui.C_ACCENT}┌────────────────────────────────────────────────────────┐{ui.C_RESET}",
        f"{ui.C_ACCENT}│ {ui.Fore.MAGENTA}       Z E R O -   F L O W   E N G I N E             {ui.C_ACCENT}│{ui.C_RESET}",
        f"{ui.C_ACCENT}│ {ui.C_RESET}🔗 Speech to text: {ui.C_GOOD}[Whisper · GPU]{ui.C_ACCENT}                     │{ui.C_RESET}",
        f"{ui.C_ACCENT}│ {ui.C_RESET}🔗 Text to speech: {ui.C_GOOD}[Kokoro-82M · CPU · loads on first read]{ui.C_RESET}",
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
    logging.info("=== Zero- Engine (merged) Boot Sequence Initiated ===")

    # Before anything can load a voice model. See the module docstring.
    voice_engine.force_cpu(CUDA_CONFLICT_REASON)

    local_flow.boot()                            # loads Whisper on the GPU
    print_boot_sequence(local_flow.get_ollama_model())
    ui.set_window_icon()
    ui.show_toast("🚀 Zero- Flow Engine Online",
                  "Dictation and read-aloud are both active.", flow_core.ENABLE_TOASTS)

    tray_icon = pystray.Icon("ZeroFlow", ui.load_tray_icon("logo_tray.ico"),
                             "Zero- Flow Engine", build_tray_menu())
    threading.Thread(target=tray_icon.run, daemon=True).start()

    local_flow.register_hotkeys()
    # After Whisper is up: the preload it starts imports torch, and that must not
    # race the CUDA load above even though Kokoro itself is pinned to the CPU.
    reader_app.register_hotkeys()
    keyboard.wait()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.critical(f"Fatal engine crash: {traceback.format_exc()}")
