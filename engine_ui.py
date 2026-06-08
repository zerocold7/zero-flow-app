import os
import sys
import time
import winsound
import ctypes
import threading
from win11toast import toast
from colorama import init, Fore, Style
import pystray
from PIL import Image, ImageDraw

init()

# Vibe Colors
C_ACCENT = Fore.CYAN
C_GOOD = Fore.GREEN
C_WARN = Fore.YELLOW
C_ERR = Fore.RED
C_RESET = Style.RESET_ALL

spinner_active = False
tray_icon = None

def update_console_title(status):
    try: ctypes.windll.kernel32.SetConsoleTitleW(f"Zero- Core [{status}]")
    except: pass

def set_window_icon(filename="logo_tray.ico"):
    """Apply the logo to the console window (title bar + taskbar entry)."""
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        if not os.path.exists(path):
            return
        hicon = ctypes.windll.user32.LoadImageW(None, path, 1, 0, 0, 0x00000010 | 0x00000040)
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd and hicon:
            ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, hicon)  # WM_SETICON, ICON_BIG
            ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hicon)  # WM_SETICON, ICON_SMALL
    except Exception:
        pass

def show_toast(title, body="", enable_toasts=True):
    if enable_toasts:
        def _fire():
            try:
                # win11toast defaults on_click/on_dismissed/on_failed to `print`,
                # so when a toast times out it leaks "(<ToastDismissalReason..>,)"
                # to the console. Pass no-op handlers to keep the console clean.
                noop = lambda *a: None
                toast(title, body, audio={"silent": "true"},
                      on_click=noop, on_dismissed=noop, on_failed=noop)
            except Exception:
                pass
        threading.Thread(target=_fire, daemon=True).start()

def play_tone(tone_type, enable_chimes=True):
    if not enable_chimes: return
    tones = {
        "start": [(1000, 120)], "stop": [(700, 120)], "mode_shift": [(1300, 100)],
        "cancel": [(500, 150), (400, 150)], "success_raw": [(1100, 80)],
        "success_polish": [(900, 60), (1200, 60)], "success_translate": [(1100, 60), (1500, 90)],
        "correction": [(1400, 50), (1800, 60)], "empty": [(440, 250)], "clean": [(1200, 80), (1400, 80)]
    }
    if tone_type in tones:
        for f, d in tones[tone_type]: winsound.Beep(f, d)

def print_boot_sequence(ollama_model, hotkeys):
    os.system('cls' if os.name == 'nt' else 'clear')
    lines = [
        f"{C_ACCENT}┌────────────────────────────────────────────────────────┐{C_RESET}",
        f"{C_ACCENT}│ {Fore.MAGENTA}          Z E R O -   F L O W   E N G I N E          {C_ACCENT}│{C_RESET}",
        f"{C_ACCENT}│ {C_RESET}🔗 Hardware Target: {C_GOOD}[NVIDIA / CPU ALLOCATED]{C_ACCENT}         │{C_RESET}",
        f"{C_ACCENT}│ {C_RESET}🔗 Neural Pipeline: {C_GOOD}[{ollama_model}]{C_ACCENT}" + (" " * max(0, 25 - len(ollama_model))) + f"│{C_RESET}",
        f"{C_ACCENT}└────────────────────────────────────────────────────────┘{C_RESET}",
        f"👉 Press {C_ACCENT}'{hotkeys['raw'].upper()}'{C_RESET} to Record:     {C_ACCENT}[RAW DICTATION]{C_RESET}",
        f"👉 Press {C_GOOD}'{hotkeys['polish'].upper()}'{C_RESET} to Record:  {C_GOOD}[AI GRAMMAR CLEANUP]{C_RESET}",
        f"👉 Press {C_WARN}'{hotkeys['translate'].upper()}'{C_RESET} to Record:{C_WARN}[AUTO-TRANSLATION MODE]{C_RESET}",
        f"👉 Press {C_ACCENT}'{hotkeys['english'].upper()}'{C_RESET} to Record:  {C_ACCENT}[FORCE ENGLISH]{C_RESET}",
        f"👉 Tap   {C_ACCENT}'{hotkeys['fix'].upper()}'{C_RESET} to auto-correct active line.",
        f"👉 Tap   {Fore.MAGENTA}'{hotkeys['maintenance'].upper()}'{C_RESET} to run AI memory maintenance.",
        f"👉 Tap   {C_GOOD}'{hotkeys['purge'].upper()}'{C_RESET} to clear the debug log & history.",
        f"👉 Press {C_ERR}'{hotkeys['panic'].upper()}'{C_RESET} to cancel the current recording.",
        f"{C_ACCENT}========================================================={C_RESET}\n"
    ]
    for line in lines:
        print(line)
        time.sleep(0.03)

def start_processing_spinner(message="AI Processing"):
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

def stop_processing_spinner():
    global spinner_active
    spinner_active = False
    time.sleep(0.15)

def create_image(color1, color2):
    image = Image.new('RGB', (64, 64), color1)
    dc = ImageDraw.Draw(image)
    dc.rectangle((16, 16, 48, 48), fill=color2)
    return image

def load_tray_icon(filename, fallback_fg='white'):
    try:
        return Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), filename))
    except Exception:
        return create_image('black', fallback_fg)

def exit_action(icon, item):
    icon.stop()
    os._exit(0)

def setup_system_tray():
    global tray_icon
    icon_image = load_tray_icon("logo_tray.ico", 'white')

    tray_icon = pystray.Icon("ZeroFlow", icon_image, "Zero- Flow Engine", menu=pystray.Menu(
        pystray.MenuItem("Exit Engine", exit_action)
    ))
    threading.Thread(target=tray_icon.run, daemon=True).start()

def set_tray_state(is_recording):
    global tray_icon
    if tray_icon:
        # Single transparent icon; recording state is shown in the tooltip title.
        tray_icon.title = "Zero- Flow Engine  ●  RECORDING" if is_recording else "Zero- Flow Engine"