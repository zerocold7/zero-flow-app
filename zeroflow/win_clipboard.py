"""The Windows clipboard, through the Win32 API: every format saved and restored, and
the engine's own writes kept out of clipboard history.

pyperclip only knew text. Saving the clipboard as text and putting that back wiped an
image or copied files on it with every dictation; and each dictation, written as
ordinary text, landed in Win+V history and cloud clipboard sync. Here a snapshot holds
every format that is plain memory (text, HTML, images as DIB, file lists, …), and
everything the engine writes carries the formats Windows reads as "keep this out of
history and the cloud".

Formats held in GDI handles (CF_BITMAP, metafiles, palettes, private formats) cannot
be copied as memory and are skipped; Windows rebuilds CF_BITMAP from the DIB.

Callers serialise with zeroflow.signals.clipboard_lock; this module only talks to
Windows. Every call opens the clipboard, does its work and closes it again.
"""
import ctypes
import logging
import time
from contextlib import contextmanager
from ctypes import wintypes

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
HWND_MESSAGE = wintypes.HWND(-3)
# Formats that are not plain memory: GDI handles, owner-drawn, and private ranges.
HANDLE_FORMATS = {2, 3, 9, 14, 0x0080, 0x0082, 0x0083, 0x008E}
PRIVATE_RANGES = (range(0x0200, 0x0300), range(0x0300, 0x0400))
# What Windows reads as "not for clipboard history or cloud sync"; each holds a DWORD 0.
PRIVATE_FORMATS = ("ExcludeClipboardContentFromMonitorProcessing",
                   "CanIncludeInClipboardHistory", "CanUploadToCloudClipboard")
# Another app may hold the clipboard for a moment: try this many times, this far apart.
OPEN_ATTEMPTS = 25
OPEN_INTERVAL = 0.02
# A snapshot larger than this keeps what it has so far (a 4K screenshot is ~33 MB).
MAX_SNAPSHOT_BYTES = 256 * 2**20

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
for _name, _restype, _argtypes in (
        ("OpenClipboard", wintypes.BOOL, [wintypes.HWND]),
        ("CloseClipboard", wintypes.BOOL, []),
        ("EmptyClipboard", wintypes.BOOL, []),
        ("EnumClipboardFormats", wintypes.UINT, [wintypes.UINT]),
        ("GetClipboardData", wintypes.HANDLE, [wintypes.UINT]),
        ("SetClipboardData", wintypes.HANDLE, [wintypes.UINT, wintypes.HANDLE]),
        ("IsClipboardFormatAvailable", wintypes.BOOL, [wintypes.UINT]),
        ("RegisterClipboardFormatW", wintypes.UINT, [wintypes.LPCWSTR]),
        ("CreateWindowExW", wintypes.HWND, [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                            wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                            ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                            wintypes.HMENU, wintypes.HINSTANCE,
                                            wintypes.LPVOID]),
        ("DestroyWindow", wintypes.BOOL, [wintypes.HWND])):
    getattr(_user32, _name).restype = _restype
    getattr(_user32, _name).argtypes = _argtypes
for _name, _restype, _argtypes in (
        ("GlobalAlloc", wintypes.HGLOBAL, [wintypes.UINT, ctypes.c_size_t]),
        ("GlobalLock", wintypes.LPVOID, [wintypes.HGLOBAL]),
        ("GlobalUnlock", wintypes.BOOL, [wintypes.HGLOBAL]),
        ("GlobalSize", ctypes.c_size_t, [wintypes.HGLOBAL]),
        ("GlobalFree", wintypes.HGLOBAL, [wintypes.HGLOBAL])):
    getattr(_kernel32, _name).restype = _restype
    getattr(_kernel32, _name).argtypes = _argtypes


class ClipboardBusy(OSError):
    """Another app kept the clipboard open."""


def format_id(name: str) -> int:
    return _user32.RegisterClipboardFormatW(name)


@contextmanager
def _opened():
    """The clipboard, open, owned by a hidden window of our own: with no owner window,
    EmptyClipboard leaves the clipboard ownerless and SetClipboardData can fail."""
    window = _user32.CreateWindowExW(0, "STATIC", None, 0, 0, 0, 0, 0, HWND_MESSAGE,
                                     None, None, None)
    try:
        for _ in range(OPEN_ATTEMPTS):
            if _user32.OpenClipboard(window):
                break
            time.sleep(OPEN_INTERVAL)
        else:
            raise ClipboardBusy(f"another app kept the clipboard open "
                                f"(error {ctypes.get_last_error()})")
        try:
            yield
        finally:
            _user32.CloseClipboard()
    finally:
        if window:
            _user32.DestroyWindow(window)


def _read(fmt: int) -> bytes | None:
    """The bytes of format `fmt` on the open clipboard, or None if it has none."""
    handle = _user32.GetClipboardData(fmt)
    if not handle:
        return None
    pointer = _kernel32.GlobalLock(handle)
    if not pointer:
        return None
    try:
        return ctypes.string_at(pointer, _kernel32.GlobalSize(handle))
    finally:
        _kernel32.GlobalUnlock(handle)


def _write(fmt: int, data: bytes) -> None:
    """Put `data` on the open clipboard as format `fmt`; Windows owns it after that."""
    handle = _kernel32.GlobalAlloc(GMEM_MOVEABLE, max(len(data), 1))
    if not handle:
        raise MemoryError("GlobalAlloc failed for the clipboard")
    pointer = _kernel32.GlobalLock(handle)
    ctypes.memmove(pointer, data, len(data))
    _kernel32.GlobalUnlock(handle)
    if not _user32.SetClipboardData(fmt, handle):
        _kernel32.GlobalFree(handle)             # still ours: Windows did not take it
        raise OSError(f"SetClipboardData failed (error {ctypes.get_last_error()})")


def _mark_private() -> None:
    for name in PRIVATE_FORMATS:
        _write(format_id(name), b"\0\0\0\0")


def _copyable(fmt: int, private: set[int]) -> bool:
    return (fmt not in HANDLE_FORMATS and fmt not in private
            and not any(fmt in r for r in PRIVATE_RANGES))


def snapshot() -> list[tuple[int, bytes]]:
    """Everything on the clipboard that can be saved, as (format, bytes) pairs."""
    private = {format_id(name) for name in PRIVATE_FORMATS}
    saved, size = [], 0
    with _opened():
        fmt = _user32.EnumClipboardFormats(0)
        while fmt:
            if _copyable(fmt, private):
                data = _read(fmt)
                if data is not None:
                    if size + len(data) > MAX_SNAPSHOT_BYTES:
                        logging.warning("The clipboard holds more than "
                                        f"{MAX_SNAPSHOT_BYTES // 2**20} MB; only part of it "
                                        "will be put back.")
                        break
                    saved.append((fmt, data))
                    size += len(data)
            fmt = _user32.EnumClipboardFormats(fmt)
    return saved


def restore(saved: list[tuple[int, bytes]]) -> None:
    """Put a snapshot back — kept out of history: it was there once already."""
    with _opened():
        _user32.EmptyClipboard()
        for fmt, data in saved:
            _write(fmt, data)
        if saved:
            _mark_private()


def set_text(text: str) -> None:
    """Put `text` on the clipboard, kept out of clipboard history and cloud sync."""
    with _opened():
        _user32.EmptyClipboard()
        _write(CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))
        _mark_private()


def clear() -> None:
    with _opened():
        _user32.EmptyClipboard()


def get_text() -> str:
    """The clipboard's text, or "" if it holds none."""
    with _opened():
        if not _user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return ""
        data = _read(CF_UNICODETEXT) or b""
    return data.decode("utf-16-le", "ignore").split("\0", 1)[0]
