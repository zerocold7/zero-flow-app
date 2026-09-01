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
MARKUP_PATTERN = re.compile(r'[*#_~\[\]`|]')
WHITESPACE_PATTERN = re.compile(r'\s+')


def fix_pronunciation(text):
    """Rewrite words the TTS voice mangles into their phonetic spelling."""
    for word, phonetic in personas.PRONUNCIATION_MAP.items():
        text = text.replace(word, phonetic)
    return text


def clean_text_instant(raw_text):
    """Strip URLs, markdown furniture and runs of whitespace. Never fails."""
    text = fix_pronunciation(raw_text)
    text = URL_PATTERN.sub('', text)
    text = MARKUP_PATTERN.sub('', text)
    text = WHITESPACE_PATTERN.sub(' ', text)
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
