"""
Zero- Flow Engine — the reader half.

    highlight text  →  [read hotkey]  →  clean  →  Kokoro speaks it

Runs only as the engine's child process (ADR 0001): the engine owns the tray, the overlay
and the Settings window, and switching "Reader on" off ends this process, which frees
the voice model's memory. It reads its settings (voice, speed, device, Smart mode) when
it starts; saving a setting restarts the engine, and with it this process.
"""
import logging
import threading
import time
import traceback

import keyboard

from reader import voice_engine
from reader.text_cleaner import clean_text_instant, clean_text_smart
from zeroflow import settings, signals, ui
from zeroflow.clipboard import POLL_INTERVAL, copy_selection

# =====================================================================
# CONFIGURATION
# =====================================================================
HOTKEY_READ = settings.HOTKEY_READ
# Shared with the dictation half on purpose: one key silences the whole engine.
HOTKEY_PANIC = settings.HOTKEYS["panic"]
SMART_MODE_DEFAULT = settings.READER_SMART_MODE

# =====================================================================
# RUNTIME STATE
# =====================================================================
# Held for one read, from the key press to the last batch queued. Each press runs on its
# own thread: a plain "busy" flag, checked and then set a few steps later, let a second
# press slip in between — two selection copies, two reads.
reading = threading.Lock()
use_smart_mode = SMART_MODE_DEFAULT   # settings: READER_SMART_MODE, read at start

# =====================================================================
# THE PIPELINE
# =====================================================================
def process_and_speak():
    """Capture the selection, clean it, and speak it."""
    if not reading.acquire(blocking=False):
        return
    try:
        _read_selection()
    finally:
        reading.release()


def _read_selection():
    if signals.is_recording():
        # Dictation has the mic open. Speaking now would be picked up and transcribed.
        logging.info("Reader: declined to speak — the dictation half is recording.")
        ui.play_tone("empty", settings.ENABLE_AUDIO_CHIMES)
        return

    try:
        # A second press restarts, never overlaps. The generation it returns goes with
        # this read: dictation starting while the text is copied or cleaned interrupts
        # again, and this read is then dropped rather than spoken into the open mic.
        generation = voice_engine.interrupt_audio()

        # Release the read key before the synthetic Ctrl+C, or Windows sees it still
        # held and the copy goes to the wrong place.
        keyboard.release(HOTKEY_READ)
        time.sleep(POLL_INTERVAL)
        text = copy_selection()
        if not text:
            logging.info("Reader: nothing selected — nothing to read.")
            ui.play_tone("empty", settings.ENABLE_AUDIO_CHIMES)
            return

        print(f"\n{ui.C_ERR}🔴 [READING]{ui.C_RESET} {text[:90]}...")
        logging.info(f"Reader captured {len(text)} chars (smart_mode={use_smart_mode}).")

        if use_smart_mode:
            _title("AI CLEANING")
            cleaned = clean_text_smart(text)
        else:
            cleaned = clean_text_instant(text)

        if signals.is_recording() or generation != voice_engine.current_generation():
            logging.info("Reader: dictation started while the text was prepared; not read.")
            return
        _title("SPEAKING")
        ui.play_tone("start", settings.ENABLE_AUDIO_CHIMES)
        voice_engine.stream_audio(cleaned, generation)
    except Exception:
        logging.error(f"Reader pipeline failed: {traceback.format_exc()}")
        traceback.print_exc()
    finally:
        _title("ONLINE")


def _title(state):
    """The engine owns the console title; this process leaves it alone."""


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
# HOTKEYS
# =====================================================================
_bound = []


def bind_keys():
    _bound.append(keyboard.add_hotkey(HOTKEY_READ, trigger_read, suppress=True))
    # Esc is deliberately NOT suppressed, so it keeps working normally everywhere.
    # The dictation half binds it too; the keyboard library runs both callbacks.
    _bound.append(keyboard.add_hotkey(HOTKEY_PANIC, voice_engine.interrupt_audio))


def unbind_keys():
    while _bound:
        try:
            keyboard.remove_hotkey(_bound.pop())
        except (KeyError, ValueError):
            pass


def follow_keys_pause(poll: float = 0.15):
    """While the Settings window is open (in the engine) this process lets go of its keys
    too, so a key pressed to be captured there is not also a read."""
    paused = False
    while True:
        now = signals.keys_paused()
        if now != paused:
            paused = now
            unbind_keys() if paused else bind_keys()
        time.sleep(poll)


def register_hotkeys():
    """Bind the reader's keys and start its background threads. Safe to call from
    either entry point."""
    # suppress=True keeps the read key out of the focused app, the same rule the
    # dictation record keys follow (a leaked F4 would reach the app mid-capture).
    bind_keys()
    threading.Thread(target=watch_for_silence_requests, daemon=True).start()
    threading.Thread(target=follow_keys_pause, daemon=True).start()
    # Warm the voice model in the background so the first read is not the slow one.
    threading.Thread(target=voice_engine.preload, daemon=True).start()

# =====================================================================
# ENTRY POINT
# =====================================================================
def main():
    """Run the reader as the engine's child (zeroflow/supervisor.py starts it). There is
    no tray and no banner here: the engine owns the tray, the overlay and the console."""
    logging.info("=== Zero- Reader Boot Sequence Initiated ===")
    register_hotkeys()
    print(f"{ui.C_ACCENT}[reader]{ui.C_RESET} read-aloud half ready "
          f"({HOTKEY_READ.upper()} to speak the selection).")
    keyboard.wait()
