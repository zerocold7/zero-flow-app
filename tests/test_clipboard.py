"""Copying the selection: one routine for F4 (read aloud) and Shift+F3 (fix a line).

The clipboard here is a stand-in, and the Ctrl+C press is replaced, so no test ever
sends a real key or touches the real clipboard.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import clipboard


class FakeClipboard:
    """pyperclip stand-in. `selection` is what a Ctrl+C would copy (None: nothing
    selected); `fill_after` polls pass before a slow app fills the clipboard."""

    def __init__(self, content="what the user had", selection="selected text", fill_after=0):
        self.content = content
        self.selection = selection
        self.fill_after = fill_after
        self.copied = False
        self.polls = 0

    def copy(self, text):
        self.content = text

    def paste(self):
        if self.copied and self.selection is not None:
            self.polls += 1
            if self.polls > self.fill_after:
                self.content = self.selection
        return self.content

    def press_copy(self):
        self.copied = True


class ClipboardTestCase(unittest.TestCase):
    def use(self, fake):
        self.keys = []
        for patcher in (mock.patch.object(clipboard, "pyperclip", fake),
                        mock.patch.object(clipboard, "_press_copy", side_effect=fake.press_copy),
                        mock.patch.object(clipboard.keyboard, "send", side_effect=self.keys.append),
                        mock.patch.object(clipboard.time, "sleep")):
            patcher.start()
            self.addCleanup(patcher.stop)
        return fake


class TestCopySelection(ClipboardTestCase):
    def test_returns_the_selection_and_restores_the_clipboard(self):
        fake = self.use(FakeClipboard())
        self.assertEqual(clipboard.copy_selection(), "selected text")
        self.assertEqual(fake.content, "what the user had")

    def test_nothing_selected_gives_none(self):
        """Not the old clipboard text: it is cleared before the copy, so leftover text
        is never mistaken for a selection."""
        fake = self.use(FakeClipboard(selection=None))
        self.assertIsNone(clipboard.copy_selection())
        self.assertEqual(fake.content, "what the user had")

    def test_a_slow_app_is_waited_for(self):
        """Shift+F3 read the clipboard once, 50 ms after Ctrl+C; slow apps were missed."""
        self.use(FakeClipboard(fill_after=10))
        self.assertEqual(clipboard.copy_selection(), "selected text")

    def test_selecting_keys_are_sent_first(self):
        self.use(FakeClipboard())
        clipboard.copy_selection(select="shift+home")
        self.assertEqual(self.keys, ["shift+home"])

    def test_holds_the_clipboard_lock(self):
        self.use(FakeClipboard())
        with mock.patch.object(clipboard, "clipboard_lock") as lock:
            clipboard.copy_selection()
        lock.assert_called_once()


class TestPaste(ClipboardTestCase):
    def test_pastes_and_restores_the_clipboard(self):
        fake = self.use(FakeClipboard())
        clipboard.paste_text("dictated", press_enter=True)
        self.assertEqual(self.keys, ["ctrl+v", "enter"])
        self.assertEqual(fake.content, "what the user had")

    def test_the_clipboard_is_restored_even_if_the_paste_fails(self):
        """A failed key send left the dictation on the clipboard, in place of what
        the user had copied."""
        fake = self.use(FakeClipboard())
        with mock.patch.object(clipboard.keyboard, "send", side_effect=OSError("no keyboard")), \
             self.assertRaises(OSError):
            clipboard.paste_text("dictated")
        self.assertEqual(fake.content, "what the user had")


class TestCallers(ClipboardTestCase):
    def test_the_reader_uses_it(self):
        from reader import app
        self.assertIs(app.copy_selection, clipboard.copy_selection)


if __name__ == "__main__":
    unittest.main()
