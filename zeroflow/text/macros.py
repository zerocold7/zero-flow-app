"""Spoken commands ("new line", "قائمة", "and send") and spoken punctuation."""
import re

from zeroflow import personas
from zeroflow.vocabulary import load_vocabulary


# Whisper punctuates what it hears, so a spoken macro rarely arrives bare: "New line.
# Hello." / "See you then, and send." Macros are matched through this punctuation.
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


def _strip_trailing(text: str, tokens: list[str]) -> tuple[str, bool]:
    """Remove a trailing trigger phrase, the comma Whisper puts before it and the mark
    after it — but not the speaker's own "!" or "?" in front. Whole words only: "a
    thousand send" is not the "and send" macro. Returns (text, matched)."""
    pattern = rf'(?i)[\s,،]*(?<!\w)(?:{_phrases(tokens)}){MACRO_PUNCT}*$'
    stripped = re.sub(pattern, '', text, count=1)
    return stripped, stripped != text


def apply_macros(text: str) -> tuple[str, bool, bool]:
    """Turn a raw transcription into the exact string to paste.

    Spoken macros ("new line", "bullet", "format code", "and send") are detected,
    stripped, and turned into formatting; spoken punctuation becomes real punctuation;
    known vocabulary is re-cased. Returns `(text, lead_newline, end_enter)` — the two
    flags being keystrokes the caller has to send, since they cannot live in a string.

    Kept separate from `inject_text` so this logic is testable without driving the
    keyboard and clipboard. See tests/test_macros.py.
    """
    macros = personas.VOICE_MACROS
    text = text.strip()

    # At most one leading macro; press_enter is the trailing one.
    lead = None
    for name in ("new_line", "bullet", "code_block"):
        text, matched = _strip_leading(text, macros[name])
        if matched:
            lead = name
            break
    lead_newline = lead == "new_line"
    lead_bullet = lead == "bullet"
    wrap_code = lead == "code_block"
    text, end_enter = _strip_trailing(text, macros["press_enter"])

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

    return text, lead_newline, end_enter
