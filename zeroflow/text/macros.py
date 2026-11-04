"""Spoken commands ("new line", "قائمة", "format code") and spoken punctuation."""
import re

from zeroflow import personas
from zeroflow.vocabulary import load_vocabulary


# Whisper punctuates what it hears, so a spoken macro rarely arrives bare: "New line.
# Hello." Macros are matched through this punctuation.
MACRO_PUNCT = r'[\s,.;:!?،؛؟…]'
TRAILING_PUNCT = re.compile(MACRO_PUNCT + r'+$')


def _phrases(tokens: list[str]) -> str:
    """Trigger phrases as one regex alternation, longest first."""
    return "|".join(re.escape(t) for t in sorted(tokens, key=len, reverse=True))


def _strip_leading(text: str, tokens: list[str]) -> tuple[str, bool]:
    """Remove a leading trigger phrase and the punctuation Whisper put after it.
    Whole words only: "Pointless" is not the "point" macro. Returns (text, matched)."""
    pattern = rf'(?i)^(?:{_phrases(tokens)})(?!\w){MACRO_PUNCT}*'
    stripped = re.sub(pattern, '', text, count=1)
    return stripped, stripped != text


def apply_macros(text: str) -> tuple[str, bool]:
    """Turn a raw transcription into the exact string to paste: take_commands, then
    format_text. Returns `(text, lead_newline)` — the flag being a keystroke the caller
    has to send, since it cannot live in a string.

    Kept separate from `inject_text` so this logic is testable without driving the
    keyboard and clipboard. See tests/test_macros.py.
    """
    words, lead = take_commands(text)
    return format_text(words, lead), lead == "new_line"


def take_commands(text: str) -> tuple[str, str | None]:
    """Strip the spoken command off the start of a transcription: `(words, lead)`.

    `lead` is the leading macro ("new_line", "bullet", "code_block") or None. Done on
    what was said, before Polish or Translate: read from the AI's answer, the command
    was the AI's to give, and Translate translated it away."""
    text = text.strip()
    for name in ("new_line", "bullet", "code_block"):           # at most one
        text, matched = _strip_leading(text, personas.VOICE_MACROS[name])
        if matched:
            return text, name
    return text, None


def format_text(text: str, lead: str | None) -> str:
    """The words, ready to paste: spoken punctuation made real, known vocabulary
    re-cased, and the leading macro's formatting (a bullet, a code span) applied."""
    lead_newline = lead == "new_line"
    lead_bullet = lead == "bullet"
    wrap_code = lead == "code_block"

    # Spoken punctuation is matched without Whisper's own closing mark, which would
    # otherwise hide it: "That is all, period." → "That is all."
    bare = TRAILING_PUNCT.sub('', text)
    if any(re.search(pattern, bare) for pattern in personas.PUNCTUATION_MAP):
        text = bare
        for pattern, replacement in personas.PUNCTUATION_MAP.items():
            text = re.sub(pattern, replacement, text)
    for word in load_vocabulary():               # normalise known-term casing
        # A function replacement, so a learned word is inserted literally: as a
        # template string, a backslash in it would raise and lose the dictation.
        text = re.sub(r'(?i)\b' + re.escape(word) + r'\b', lambda _, word=word: word, text)

    text = text.strip()
    if wrap_code:
        text = f"`{text}`"
    if lead_bullet:
        text = "• " + text
    elif not lead_newline and text and not wrap_code:
        text = " " + text                        # keep spacing against the previous word

    return text
