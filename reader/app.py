"""
Zero- Flow Engine — the reader half.

    highlight text  →  [read hotkey]  →  clean  →  Kokoro speaks it

Written so it can be driven two ways: on its own (`python -m reader`, which calls
`main()`), or spliced into the merged single-process engine (`zero_flow.py`, which
calls `register_hotkeys()` and `tray_items()` and supplies its own console and tray).
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
    import engine_ui as ui
    import flow_core
    import flow_signals as signals
    from reader import voice_engine
    from reader.clipboard_tool import capture_highlighted_text
    from reader.text_cleaner import clean_text_instant, clean_text_smart
except ImportError as e:
    print(f"❌ Critical error: Missing local module: {e}")
    print("   Run the reader from the repository root: python -m reader")
    sys.exit(1)

# =====================================================================
# CONFIGURATION
# =====================================================================
HOTKEY_READ = os.getenv("HOTKEY_READ", "f4")
# Shared with the dictation half on purpose: one key silences the whole engine.
HOTKEY_PANIC = os.getenv("HOTKEY_PANIC", "esc")
# Off by default: the regex clean is instant, the LLM pass costs a few seconds.
SMART_MODE_DEFAULT = os.getenv("READER_SMART_MODE", "False").lower() in ('true', '1', 't')

# =====================================================================
# RUNTIME STATE
# =====================================================================
is_processing = False
is_suspended = False
use_smart_mode = SMART_MODE_DEFAULT

# =====================================================================
# THE PIPELINE
# =====================================================================
def process_and_speak():
    """Capture the selection, clean it, and speak it."""
    global is_processing
    if is_processing or is_suspended:
        return

    if signals.is_recording():
        # Dictation has the mic open. Speaking now would be picked up and transcribed.
        logging.info("Reader: declined to speak — the dictation half is recording.")
        ui.play_tone("empty", flow_core.ENABLE_AUDIO_CHIMES)
        return

    is_processing = True
    try:
        voice_engine.interrupt_audio()           # a second press restarts, never overlaps

        text = capture_highlighted_text(release_key=HOTKEY_READ)
        if not text:
            logging.info("Reader: nothing selected — nothing to read.")
            ui.play_tone("empty", flow_core.ENABLE_AUDIO_CHIMES)
            return

        print(f"\n{ui.C_ERR}🔴 [READING]{ui.C_RESET} {text[:90]}...")
        logging.info(f"Reader captured {len(text)} chars (smart_mode={use_smart_mode}).")

        if use_smart_mode:
            ui.update_console_title("OLLAMA PROCESSING")
            cleaned = clean_text_smart(text)
        else:
            cleaned = clean_text_instant(text)

        ui.update_console_title("SPEAKING")
        ui.play_tone("start", flow_core.ENABLE_AUDIO_CHIMES)
        voice_engine.stream_audio(cleaned)
    except Exception:
        logging.error(f"Reader pipeline failed: {traceback.format_exc()}")
        traceback.print_exc()
    finally:
        ui.update_console_title("ONLINE")
        is_processing = False


def trigger_read():
    threading.Thread(target=process_and_speak, daemon=True).start()


def watch_for_silence_requests():
    """Stop speaking the instant the dictation half opens the microphone.

    Blocks on a Windows named event, so this thread costs nothing while idle, and it
    works whether the halves are two processes or one. If signalling is unavailable
    the thread simply exits and the two behave independently, as they used to.
    """
    if not signals.available():
        logging.warning("Cross-process signalling unavailable — the reader will not "
                        "auto-silence when dictation starts.")
        return
    while True:
        if signals.wait_for_silence_request():
            voice_engine.interrupt_audio()
            logging.info("Reader silenced: the dictation half started recording.")

# =====================================================================
# TRAY MENU
# =====================================================================
def toggle_suspend(icon, item):
    global is_suspended
    is_suspended = not is_suspended
    if is_suspended:
        voice_engine.interrupt_audio()
    print(f"{ui.C_ACCENT}🔵 [Settings]{ui.C_RESET} Reader {'SUSPENDED' if is_suspended else 'ACTIVE'}")


def toggle_smart_mode(icon, item):
    global use_smart_mode
    use_smart_mode = not use_smart_mode
    print(f"{ui.C_ACCENT}🔵 [Settings]{ui.C_RESET} Smart LLM cleaning is now "
          f"{'ON' if use_smart_mode else 'OFF'}")


def change_voice(icon, item):
    voice_engine.set_voice(item.text)


def exit_application(icon, item):
    voice_engine.interrupt_audio()
    icon.stop()
    os._exit(0)


def tray_items():
    """The reader's menu entries, without an Exit item — so the merged engine can
    splice them into its single tray menu and own the exit itself."""
    voice_items = [
        MenuItem(label, change_voice, radio=True,
                 checked=(lambda lbl: lambda item: voice_engine.current_voice
                          == voice_engine.VOICES[lbl])(label))
        for label in voice_engine.VOICES
    ]
    return (
        MenuItem("Suspend Reader", toggle_suspend, checked=lambda item: is_suspended),
        MenuItem("Smart LLM Cleaning", toggle_smart_mode, checked=lambda item: use_smart_mode),
        pystray.Menu.SEPARATOR,
        *voice_items,
    )


def build_tray_menu():
    return pystray.Menu(*tray_items(), pystray.Menu.SEPARATOR,
                        MenuItem("Exit Reader", exit_application))

# =====================================================================
# HOTKEYS
# =====================================================================
def register_hotkeys():
    """Bind the reader's keys and start its background threads. Safe to call from
    either entry point."""
    # suppress=True keeps the read key out of the focused app, the same rule the
    # dictation record keys follow (a leaked F4 would reach the app mid-capture).
    keyboard.add_hotkey(HOTKEY_READ, trigger_read, suppress=True)
    # Esc is deliberately NOT suppressed, so it keeps working normally everywhere.
    # The dictation half binds it too; the keyboard library runs both callbacks.
    keyboard.add_hotkey(HOTKEY_PANIC, voice_engine.interrupt_audio)
    threading.Thread(target=watch_for_silence_requests, daemon=True).start()

# =====================================================================
# CONSOLE
# =====================================================================
def print_boot_sequence():
    os.system('cls' if os.name == 'nt' else 'clear')
    llm = flow_core.OLLAMA_MODEL_NAME or "auto-discovered on first use"
    print(f"{ui.C_ACCENT}┌────────────────────────────────────────────────────────┐{ui.C_RESET}")
    print(f"{ui.C_ACCENT}│ {ui.Fore.MAGENTA}     Z E R O -   F L O W   ·   R E A D E R           {ui.C_ACCENT}│{ui.C_RESET}")
    print(f"{ui.C_ACCENT}│ {ui.C_RESET}🔗 Voice model: {ui.C_GOOD}[Kokoro-82M · loads on first read]{ui.C_ACCENT}      │{ui.C_RESET}")
    print(f"{ui.C_ACCENT}│ {ui.C_RESET}🔗 Smart clean: {ui.C_GOOD}[{llm}]{ui.C_RESET}")
    print(f"{ui.C_ACCENT}└────────────────────────────────────────────────────────┘{ui.C_RESET}")
    print(f"  {ui.C_ACCENT}ACTIONS{ui.C_RESET}")
    print(f"   {ui.C_GOOD}'{HOTKEY_READ.upper()}'{ui.C_RESET} read the highlighted text   "
          f"{ui.C_ERR}'{HOTKEY_PANIC.upper()}'{ui.C_RESET} silence")
    print(f"   Voice, smart cleaning and suspend live in the tray menu.")
    print(f"{ui.C_ACCENT}========================================================={ui.C_RESET}\n")

# =====================================================================
# STANDALONE ENTRY POINT
# =====================================================================
def main():
    logging.info("=== Zero- Reader Boot Sequence Initiated ===")
    ui.update_console_title("ONLINE")
    print_boot_sequence()
    ui.set_window_icon()
    ui.show_toast("🔊 Zero- Reader Online", f"Press {HOTKEY_READ.upper()} to read the selection.",
                  flow_core.ENABLE_TOASTS)

    tray_icon = pystray.Icon("ZeroFlowReader", ui.load_tray_icon("logo_tray.ico"),
                             "Zero- Flow Reader", build_tray_menu())
    threading.Thread(target=tray_icon.run, daemon=True).start()

    register_hotkeys()
    keyboard.wait()
