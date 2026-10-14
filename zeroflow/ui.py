"""
Zero- Flow Engine — shared console and desktop UI.

Everything the user sees or hears that is not the dictated text or the spoken voice:
console colours and the boot banner, the console title and window icon, the "AI
Processing" spinner, audio chimes, Windows toast notifications, and the standalone
dictation half's tray icon. (Under `zero_flow.py` the tray icon belongs to the reader
child instead — see reader/app.py.)

Chimes and toasts run on their own threads: a blocking call on a keyboard-hook thread
freezes the whole keyboard. `win11toast` is imported lazily for a load-order reason
explained in show_toast().
"""
import logging
import os
import sys
import time
import winsound
import ctypes
import threading
from colorama import init, Fore, Style
import pystray
from PIL import Image, ImageDraw

from zeroflow.paths import BASE_DIR

init()

# Vibe Colors
C_ACCENT = Fore.CYAN
C_GOOD = Fore.GREEN
C_WARN = Fore.YELLOW
C_ERR = Fore.RED
C_RESET = Style.RESET_ALL

spinner_active = False
tray_icon = None

def update_console_title(status: str) -> None:
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(f"Zero- Core [{status}]")
    except Exception:                            # no console (started hidden)
        pass

def set_window_icon(filename: str = "logo_tray.ico") -> None:
    """Apply the logo to the console window (title bar + taskbar entry)."""
    try:
        path = os.path.join(BASE_DIR, filename)
        if not os.path.exists(path):
            return
        hicon = ctypes.windll.user32.LoadImageW(None, path, 1, 0, 0, 0x00000010 | 0x00000040)
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd and hicon:
            ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, hicon)  # WM_SETICON, ICON_BIG
            ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hicon)  # WM_SETICON, ICON_SMALL
    except Exception:
        pass

MB_ICONERROR = 0x10
MB_ICONINFORMATION = 0x40
MB_SETFOREGROUND = 0x10000
MB_TOPMOST = 0x40000

def alert(title: str, text: str, icon: int = MB_ICONERROR) -> None:
    """A Windows message box, which blocks until dismissed. For the few things that
    must reach the user even when the engine was started hidden (Launch_*_Silent.vbs):
    there, a console message or a toast that times out is never seen."""
    try:
        ctypes.windll.user32.MessageBoxW(None, text, title, icon | MB_SETFOREGROUND | MB_TOPMOST)
    except Exception:
        pass

def report_setting_problems(problems: list[str], enable_toasts: bool = True) -> None:
    """Say which .env settings were ignored, and why — in the console, the log and a
    toast, since a hidden engine's console is never seen."""
    for problem in problems:
        logging.warning(f"Setting ignored: {problem}")
        print(f"{C_WARN}⚠️  {problem}{C_RESET}")
    if problems:
        show_toast("⚠️ Check your settings",
                   f"{len(problems)} setting(s) in .env were ignored — the defaults are "
                   f"used. Details in the log.", enable_toasts)

def already_running(what: str = "Zero- Flow") -> None:
    """Tell the user a second copy was not started, and why."""
    print(f"{C_WARN}{what} is already running — look for its icon by the clock. "
          f"This copy will close.{C_RESET}")
    alert(what, f"{what} is already running — look for its icon by the clock.\n\n"
                f"Running two copies would paste every dictation twice, so this one "
                f"has not started.", MB_ICONINFORMATION)

def show_toast(title: str, body: str = "", enable_toasts: bool = True) -> None:
    if enable_toasts:
        def _fire():
            try:
                # Imported here, not at module scope, and this is load-bearing:
                # win11toast pulls in WinRT native libraries, and if that happens
                # before faster-whisper claims its CUDA DLLs, CTranslate2 segfaults
                # the entire process when it later loads the model on the GPU. By the
                # time a toast fires, Whisper is long since loaded and it is safe.
                from win11toast import toast
                # win11toast defaults on_click/on_dismissed/on_failed to `print`,
                # so when a toast times out it leaks "(<ToastDismissalReason..>,)"
                # to the console. Pass no-op handlers to keep the console clean.
                def ignore(*_):
                    return None
                toast(title, body, audio={"silent": "true"},
                      on_click=ignore, on_dismissed=ignore, on_failed=ignore)
            except Exception:
                pass
        threading.Thread(target=_fire, daemon=True).start()

def play_tone(tone_type: str, enable_chimes: bool = True) -> None:
    if not enable_chimes:
        return
    tones = {
        "start": [(1000, 120)], "stop": [(700, 120)],
        "cancel": [(500, 150), (400, 150)], "success_raw": [(1100, 80)],
        "success_polish": [(900, 60), (1200, 60)], "success_translate": [(1100, 60), (1500, 90)],
        "correction": [(1400, 50), (1800, 60)], "empty": [(440, 250)], "clean": [(1200, 80), (1400, 80)]
    }
    seq = tones.get(tone_type)
    if not seq:
        return
    # winsound.Beep blocks for the tone's duration; play it off-thread so it never
    # stalls a keyboard-hotkey callback (a stalled callback freezes the keyboard).
    def _beep():
        for f, d in seq:
            winsound.Beep(f, d)
    threading.Thread(target=_beep, daemon=True).start()

def print_banner(title: str, about: list[tuple[str, str]], sections: list) -> None:
    """The start-up banner, for all three ways of running the engine.

    `about` is (label, value) pairs — what loaded where ("Speech to text", "Whisper
    large-v3 · GPU · float16"), so a tuning change is visible at a glance. `sections`
    is (heading, note, rows); a row is a list of (key, what it does, colour), or a
    plain line of text."""
    os.system('cls' if os.name == 'nt' else 'clear')
    rule = "─" * 56
    lines = [f"{C_ACCENT}┌{rule}┐{C_RESET}",
             f"{C_ACCENT}│ {Fore.MAGENTA}{title.center(54)}{C_ACCENT} │{C_RESET}"]
    lines += [f"{C_ACCENT}│ {C_RESET}🔗 {label}: {C_GOOD}[{value}]{C_RESET}" for label, value in about]
    lines.append(f"{C_ACCENT}└{rule}┘{C_RESET}")
    for heading, note, rows in sections:
        lines.append(f"  {C_ACCENT}{heading}{C_RESET}" + (f"   ({note})" if note else ""))
        for row in rows:
            lines.append("   " + (row if isinstance(row, str) else "   ".join(
                f"{colour}'{key.upper()}'{C_RESET} {what}" for key, what, colour in row)))
    lines.append(f"{C_ACCENT}{'=' * 57}{C_RESET}\n")
    for line in lines:
        print(line)
        time.sleep(0.03)

def start_processing_spinner(message: str = "AI Processing") -> None:
    global spinner_active
    spinner_active = True
    def spin():
        chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        i = 0
        while spinner_active:
            sys.stdout.write(f"\r{C_WARN}[{chars[i % len(chars)]}] {message}...{C_RESET}")
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1
        sys.stdout.write("\r" + " " * 50 + "\r")
    threading.Thread(target=spin, daemon=True).start()

def stop_processing_spinner() -> None:
    global spinner_active
    spinner_active = False
    time.sleep(0.15)

def create_image(color1: str, color2: str) -> Image.Image:
    image = Image.new('RGB', (64, 64), color1)
    dc = ImageDraw.Draw(image)
    dc.rectangle((16, 16, 48, 48), fill=color2)
    return image

def load_tray_icon(filename: str, fallback_fg: str = 'white') -> Image.Image:
    try:
        return Image.open(os.path.join(BASE_DIR, filename))
    except Exception:
        return create_image('black', fallback_fg)

def exit_action(icon, item):
    icon.stop()
    os._exit(0)

def setup_system_tray() -> None:
    global tray_icon
    icon_image = load_tray_icon("logo_tray.ico", 'white')

    tray_icon = pystray.Icon("ZeroFlow", icon_image, "Zero- Flow Engine", menu=pystray.Menu(
        pystray.MenuItem("Exit Engine", exit_action)
    ))
    threading.Thread(target=tray_icon.run, daemon=True).start()

def set_tray_state(is_recording: bool) -> None:
    global tray_icon
    if tray_icon:
        # Single transparent icon; recording state is shown in the tooltip title.
        tray_icon.title = "Zero- Flow Engine  ●  RECORDING" if is_recording else "Zero- Flow Engine"