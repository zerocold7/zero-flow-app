"""The learned vocabulary: names and terms Whisper is primed with, and the AI keeps
spelled right. Stored one per line in flow_vocabulary.txt."""
import logging
import os
import re
import threading

from zeroflow import personas, ui
from zeroflow.paths import VOCAB_CACHE_FILE
from zeroflow.settings import ENABLE_TOASTS
from zeroflow.text.language import FOREIGN_SCRIPT
LEARN_PATTERN = re.compile(r'\[LEARN:\s*(.*?)\]')


# Held around every write to the vocabulary file: a learned word is appended after a
# Polish while Shift+F1 may be rewriting the whole file. Reentrant, because the
# rewrite's own LLM call can learn a word on the same thread.
VOCAB_LOCK = threading.RLock()


def load_vocabulary() -> list[str]:
    """Base vocabulary plus any words the LLM has learned over time."""
    vocab = set(personas.BASE_VOCABULARY)
    if os.path.exists(VOCAB_CACHE_FILE):
        try:
            with open(VOCAB_CACHE_FILE, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        vocab.add(line.strip())
        except Exception:
            pass
    return list(vocab)


def _squash(text: str) -> str:
    return re.sub(r"[\s\-_.]", "", text.lower())


def append_vocabulary_word(word: str) -> None:
    """Add one word to the learned-vocabulary file on a line of its own. Call with
    VOCAB_LOCK held. A file that ends without a newline (hand-edited, say) would
    otherwise glue the new word onto the last one: "Visa" + "Kokoro" = "VisaKokoro"."""
    needs_newline = False
    if os.path.exists(VOCAB_CACHE_FILE) and os.path.getsize(VOCAB_CACHE_FILE) > 0:
        with open(VOCAB_CACHE_FILE, "rb") as f:
            f.seek(-1, os.SEEK_END)
            needs_newline = f.read(1) != b"\n"
    with open(VOCAB_CACHE_FILE, "a", encoding="utf-8") as f:
        f.write(("\n" if needs_newline else "") + f"{word}\n")


def _absorb_learned_word(output: str, heard: str | None = None) -> str:
    """If the LLM tagged a new term as `[LEARN: word]`, persist it and strip the tag.

    `heard` is what was actually said. A term is only learned if it appears there
    (ignoring case and spacing, so "chroma db" still teaches "ChromaDB"): models also
    "learn" words nobody said — a misheard Arabic word, or a Chinese one — and every
    learned word is fed to Whisper as a hint on each later dictation."""
    match = LEARN_PATTERN.search(output)
    if not match:
        return output
    word = match.group(1).strip()
    if word and (FOREIGN_SCRIPT.search(word)
                 or (heard is not None and _squash(word) not in _squash(heard))):
        logging.info(f"Ignored a learned word that was not in what was said: {word!r}")
    elif word:
        with VOCAB_LOCK:
            learned = word not in load_vocabulary()
            if learned:
                append_vocabulary_word(word)
        if learned:
            ui.show_toast("🧠 Learned New Word", f"Added '{word}'", ENABLE_TOASTS)
    return LEARN_PATTERN.sub('', output).strip()


# LLMs like to answer "list the words" with "- word" or "1. word"; keep only the word.
LIST_MARKER = re.compile(r'^\s*(?:[-*•]|\d+[.)])\s+')


# A vocabulary term is a name or phrase ("Visual Studio Code"), never a sentence.
MAX_TERM_WORDS = 4


def vocabulary_terms(llm_output: str | None) -> list[str]:
    """The terms in the LLM's answer to "clean up this list", without its chatter.

    Models wrap the list in sentences ("Here is the cleaned list:", "I removed the
    duplicates..."). Kept, each became a "word" and was fed to Whisper as a hint on
    every dictation. A term is short and never introduces something with a colon."""
    terms = []
    for line in (llm_output or "").splitlines():
        term = LIST_MARKER.sub('', line).strip()
        if term and not term.endswith(":") and len(term.split()) <= MAX_TERM_WORDS:
            terms.append(term)
    return terms
