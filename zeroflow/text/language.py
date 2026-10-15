"""Which language a text is in, and checking the AI answered in the right one."""
import logging
import re

from zeroflow import ui


# Chinese, Japanese and Korean script. The engine only ever wants English or Arabic, and
# some models (qwen2.5) slip into Chinese when handed Arabic.
FOREIGN_SCRIPT = re.compile(r'[\u3040-\u30FF\u3400-\u9FFF\uAC00-\uD7AF\uF900-\uFAFF]')
ARABIC_LETTERS = re.compile(r'[\u0621-\u064A]')
LATIN_LETTERS = re.compile(r'[A-Za-z]')


# Arabic vowel marks and shadda, stripped from the AI's Arabic: models add them unasked
# ("لنُحدِّث"), and prose is written without. Tanween fath (U+064B) is kept — "جدًا" and
# "شكرًا" spell it as standard.
ARABIC_MARKS = re.compile(r'[\u064C-\u0652\u0670]')


# All of them, tanween fath and tatweel included — for comparing words, not for text.
ARABIC_MARKS_ALL = re.compile(r'[\u064B-\u0652\u0670\u0640]')


def plain_words(text: str) -> list[str]:
    """Words as compared with STOCK_ENDINGS: lower case, no punctuation, no Arabic vowel
    marks, one spelling for the alef, ya and ta marbuta variants."""
    text = ARABIC_MARKS_ALL.sub("", text.lower())
    for variants, plain in (("أإآ", "ا"), ("ى", "ي"), ("ة", "ه")):
        text = re.sub(f"[{variants}]", plain, text)
    return re.sub(r"[^\w\s]|_", " ", text).split()


def checked_ai_output(output: str, original: str, lang: str) -> str:
    """The AI's text if it is in the language asked for — otherwise the original words.

    Better to paste what you said, unpolished, than to paste Chinese: qwen2.5:7b
    answered Arabic Polish in Chinese in 5 tries out of 5. Arabic output also loses the
    vowel marks models add unasked."""
    if output == original:                       # nothing changed: nothing to check
        return output
    wanted = ARABIC_LETTERS if lang == "ar" else LATIN_LETTERS
    if FOREIGN_SCRIPT.search(output) or not wanted.search(output):
        logging.warning(f"The AI did not answer in '{lang}'; pasting the original instead: "
                        f"{output[:120]!r}")
        print(f"{ui.C_WARN}⚠️  The AI answered in the wrong language — pasting your own words.{ui.C_RESET}")
        return original
    return ARABIC_MARKS.sub("", output) if lang == "ar" else output
