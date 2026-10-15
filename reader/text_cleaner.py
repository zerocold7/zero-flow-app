"""
Clean captured text before it is spoken.

Two levels:
    clean_text_instant  — regex only, no network, effectively free
    clean_text_smart    — one pass through the engine's AI model, with an automatic
                          fall back to the instant clean

The AI call goes through `zeroflow.llm.ask_ai`, the same as dictation's: whichever
provider AI_PROVIDER names, with its failures reported the same way.
"""
import logging
import re

from zeroflow import personas, settings
from zeroflow import llm
from zeroflow.text import URL_PATTERN  # shared: also strips www. addresses

# Above this length the AI pass is skipped: a local model needs several seconds per
# thousand characters, which is longer than the wait for speech to simply start.
SMART_MODE_MAX_CHARS = settings.READER_SMART_MAX_CHARS
# The reader is interactive, so it waits less patiently than the dictation engine.
READER_LLM_TIMEOUT = settings.READER_LLM_TIMEOUT

# Footnote/reference markers, dropped whole. Stripping the brackets alone would leave
# the digits behind, and the voice would read "[1]" aloud as "one".
FOOTNOTE_PATTERN = re.compile(r'\[\s*\d+(?:\s*[,–-]\s*\d+)*\s*\]')
MARKUP_PATTERN = re.compile(r'[*#_~\[\]`|]')
WHITESPACE_PATTERN = re.compile(r'\s+')
# Removing a marker mid-sentence strands a space in front of the punctuation
# ("disputed ."), which the voice reads as a stumble.
ORPHAN_SPACE_PATTERN = re.compile(r'\s+([.,;:!?،؛؟])')

# Built once from personas.PRONUNCIATION_MAP. Case-insensitive with word boundaries,
# because the map is written in one casing and real text is not: "aqeeq" was being
# fixed while "Aqeeq" sailed through untouched.
_PRONUNCIATION_RE = re.compile(
    r'\b(?:' + "|".join(sorted((re.escape(w) for w in personas.PRONUNCIATION_MAP),
                                  key=len, reverse=True)) + r')\b',
    re.IGNORECASE) if personas.PRONUNCIATION_MAP else None
_PRONUNCIATION_LOOKUP = {w.lower(): p for w, p in personas.PRONUNCIATION_MAP.items()}


def fix_pronunciation(text):
    """Rewrite words the TTS voice mangles into their phonetic spelling."""
    if _PRONUNCIATION_RE is None:
        return text
    return _PRONUNCIATION_RE.sub(
        lambda m: _PRONUNCIATION_LOOKUP[m.group(0).lower()], text)


def clean_text_instant(raw_text):
    """Strip URLs, markdown furniture and runs of whitespace. Never fails."""
    text = fix_pronunciation(raw_text)
    text = URL_PATTERN.sub('', text)
    text = FOOTNOTE_PATTERN.sub('', text)        # before the markup pass, which would
    text = MARKUP_PATTERN.sub('', text)          # leave the bare digits behind
    text = WHITESPACE_PATTERN.sub(' ', text)
    text = ORPHAN_SPACE_PATTERN.sub(r'\1', text)
    return text.strip()


def clean_text_smart(raw_text):
    """Let the AI strip page furniture, falling back to the instant clean when it
    gives no answer (unreachable, too slow) or hands the text back unchanged — the
    reader always speaks something.
    """
    prepared = fix_pronunciation(raw_text)
    if len(prepared) > SMART_MODE_MAX_CHARS:
        logging.info(f"Reader: {len(prepared)} chars exceeds the smart-mode limit — regex clean only.")
        return clean_text_instant(raw_text)

    output = llm.ask_ai(prepared, None, personas.READER_CLEANUP_PROMPT,
                        timeout=READER_LLM_TIMEOUT)
    if not output or output.strip() == prepared.strip():
        logging.info("Reader: smart clean returned nothing new — falling back to regex clean.")
        return clean_text_instant(raw_text)

    # The model occasionally echoes markdown back; run the cheap pass over its output.
    return WHITESPACE_PATTERN.sub(' ', MARKUP_PATTERN.sub('', output)).strip()
