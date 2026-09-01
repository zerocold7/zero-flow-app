"""
Clean captured text before it is spoken.

Two levels:
    clean_text_instant  — regex only, no network, effectively free
    clean_text_smart    — one pass through the shared local LLM, with an automatic
                          fall back to the instant clean

The LLM call goes through `flow_core.query_ollama`, so the reader inherits the
engine's model discovery, the `OLLAMA_MODEL_NAME` pin from `.env`, the offline
fallback and the console spinner. There is no second Ollama client.
"""
import logging
import os
import re

import personas
import flow_core

# Above this length the LLM pass is skipped: a local 7B model needs several seconds
# per thousand characters, which is longer than the wait for speech to simply start.
SMART_MODE_MAX_CHARS = int(os.getenv("READER_SMART_MAX_CHARS", 1000))
# The reader is interactive, so it waits less patiently than the dictation engine.
READER_LLM_TIMEOUT = float(os.getenv("READER_LLM_TIMEOUT", 10.0))

URL_PATTERN = re.compile(r'http[s]?://\S+')
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
    r'\b(?:%s)\b' % "|".join(sorted((re.escape(w) for w in personas.PRONUNCIATION_MAP),
                                     key=len, reverse=True)),
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
    """Let the local LLM strip page furniture, falling back to the instant clean.

    `query_ollama` returns its input unchanged when Ollama is unreachable or slow,
    so an unchanged result is treated as a miss and cleaned with regex instead —
    the reader always speaks something.
    """
    prepared = fix_pronunciation(raw_text)
    if len(prepared) > SMART_MODE_MAX_CHARS:
        logging.info(f"Reader: {len(prepared)} chars exceeds the smart-mode limit — regex clean only.")
        return clean_text_instant(raw_text)

    output = flow_core.query_ollama(prepared, None, personas.READER_CLEANUP_PROMPT,
                                    timeout=READER_LLM_TIMEOUT)
    if not output or output.strip() == prepared.strip():
        logging.info("Reader: smart clean returned nothing new — falling back to regex clean.")
        return clean_text_instant(raw_text)

    # The model occasionally echoes markdown back; run the cheap pass over its output.
    return WHITESPACE_PATTERN.sub(' ', MARKUP_PATTERN.sub('', output)).strip()
