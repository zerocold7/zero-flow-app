"""The real Windows clipboard: everything on it comes back, and the engine's own text
stays out of clipboard history.

pyperclip saved and restored text only: an image or copied files on the clipboard
were gone after every dictation, and each dictation landed in Win+V history and
cloud clipboard sync.

These tests use the real clipboard, so they are off unless ZEROFLOW_REAL_CLIPBOARD=1
(whatever was on it is put back afterwards). Keys are never sent.
"""
import os
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import clipboard, win_clipboard

CF_DIB = 8
CF_UNICODETEXT = 13


def tiny_dib() -> bytes:
    """A 2×2 32-bit bitmap, as CF_DIB holds it: BITMAPINFOHEADER, then the pixels."""
    header = struct.pack("<IiiHHIIiiII", 40, 2, 2, 1, 32, 0, 16, 0, 0, 0, 0)
    return header + bytes([0, 0, 255, 0, 0, 255, 0, 0, 255, 0, 0, 0, 255, 255, 255, 0])


@unittest.skipUnless(os.getenv("ZEROFLOW_REAL_CLIPBOARD") == "1",
                     "uses the real clipboard; set ZEROFLOW_REAL_CLIPBOARD=1")
class TestRealClipboard(unittest.TestCase):
    def setUp(self):
        self.users = win_clipboard.snapshot()
        self.addCleanup(win_clipboard.restore, self.users)

    def formats(self) -> dict:
        return dict(win_clipboard.snapshot())

    def test_text_goes_in_and_comes_out(self):
        win_clipboard.set_text("héllo مرحبا")
        self.assertEqual(win_clipboard.get_text(), "héllo مرحبا")

    def test_the_engines_text_is_kept_out_of_history(self):
        win_clipboard.set_text("dictated")
        for name in win_clipboard.PRIVATE_FORMATS:
            fmt = win_clipboard.format_id(name)
            with win_clipboard._opened():
                on_it = win_clipboard._user32.IsClipboardFormatAvailable(fmt)
            self.assertTrue(on_it, name)

    def test_an_image_survives_a_dictation(self):
        win_clipboard.restore([(CF_DIB, tiny_dib())])
        with mock.patch.object(clipboard.keyboard, "send"), \
             mock.patch.object(clipboard.time, "sleep"):
            clipboard.paste_text("dictated")
        self.assertEqual(self.formats().get(CF_DIB), tiny_dib())
        self.assertEqual(win_clipboard.get_text(), "")

    def test_an_image_survives_a_selection_copy(self):
        win_clipboard.restore([(CF_DIB, tiny_dib())])
        with mock.patch.object(clipboard, "_press_copy"), \
             mock.patch.object(clipboard.time, "sleep"):
            self.assertIsNone(clipboard.copy_selection())
        self.assertEqual(self.formats().get(CF_DIB), tiny_dib())

    def test_text_the_user_copied_comes_back(self):
        win_clipboard.restore([(CF_UNICODETEXT, "copied by you\0".encode("utf-16-le"))])
        with mock.patch.object(clipboard.keyboard, "send"), \
             mock.patch.object(clipboard.time, "sleep"):
            clipboard.paste_text("dictated")
        self.assertEqual(win_clipboard.get_text(), "copied by you")

    def test_an_empty_clipboard_stays_empty(self):
        win_clipboard.restore([])
        self.assertEqual(win_clipboard.snapshot(), [])


if __name__ == "__main__":
    unittest.main()
