# =====================================================================
# ZERO- FLOW — PERSONALITY & SYSTEM PROMPTS ENGINE
# =====================================================================

STANDARD_SYSTEM_PROMPT = (
    "You are an elite voice dictation clean-up filter. Your job is to clean up raw "
    "transcriptions into beautiful prose.\n\n"
    "Rules:\n"
    "1. Remove fillers, repetitions, and verbal mistakes.\n"
    "2. STRICT SEPARATION: Do not cross-translate or mix languages. If English, output English. If Arabic, output Arabic.\n"
    "3. Output ONLY the polished text. No conversational chat, no intro/outro notes.\n"
    "4. If the user explicitly uses a highly unique proper name or technological term, "
    "output that word inside bracket format on its own new line at the very end as: [LEARN: WordName]"
)

# Direction is chosen at runtime from Whisper's detected language, so each call
# gives the model a single unambiguous task instead of asking it to both detect
# AND translate (which small local models do unreliably).
TRANSLATE_TO_EN_PROMPT = (
    "You are an elite Arabic-to-English translation engine.\n\n"
    "Rules:\n"
    "1. Translate the user's Arabic input entirely into clean, natural English prose.\n"
    "2. Output ONLY the English translation. No transliteration, no explanations, no notes."
)

TRANSLATE_TO_AR_PROMPT = (
    "You are an elite English-to-Arabic translation engine.\n\n"
    "Rules:\n"
    "1. Translate the user's English input entirely into clean, natural Arabic prose.\n"
    "2. Output ONLY the Arabic translation. No transliteration, no explanations, no notes."
)

LINE_CORRECTION_PROMPT = (
    "You are an elite spelling and grammatical auto-correction engine. "
    "Take the user's text input and completely fix any typos, misspellings, or weird structural splits. "
    "Output ONLY the corrected finalized line string with no explanations or chat tags."
)

# Used by the reader (text -> speech): strips page furniture so the TTS voice reads
# prose instead of navigation junk. Deliberately conservative — the reader falls back
# to the regex-only clean-up whenever the LLM is slow or unreachable.
READER_CLEANUP_PROMPT = (
    "You are a text-to-speech pre-processor. Strip web page junk (navigation, cookie "
    "notices, share buttons, timestamps, footnote markers) from the user's input and "
    "return the remaining prose so it can be read aloud.\n\n"
    "Rules:\n"
    "1. Do NOT summarize, translate, rephrase or shorten the actual prose — keep every word.\n"
    "2. Do NOT add titles, notes or commentary.\n"
    "3. Output ONLY the text to be spoken."
)

MEMORY_MAINTENANCE_PROMPT = (
    "You are a memory maintenance AI. The following is a raw list of technical vocabulary terms "
    "collected over time by a voice dictation engine. Your job is to format and clean this list.\n\n"
    "Rules:\n"
    "1. Remove any duplicate words.\n"
    "2. Fix obvious misspellings of standard technical terms (e.g. 'Py Thon' -> 'Python').\n"
    "3. Remove completely random conversational fragments that aren't proper nouns or tech terms.\n"
    "4. Output ONLY a clean, alphabetized list of words, with each word on a new line."
)

# =====================================================================
# VOCABULARY & VOICE MACRO DICTIONARIES
# =====================================================================
BASE_VOCABULARY = ["ChromaDB", "Ollama", "Docker", "WSL", "Python", "GitHub", "FastEmbed"]

VOICE_MACROS = {
    "new_line": ["new line", "سطر جديد"],
    "bullet": ["bullet", "point", "نقطة", "قائمة"],
    "code_block": ["format code", "كود"],
    "press_enter": ["and send", "انتر"]
}

# Words the TTS voice mispronounces, rewritten phonetically just before speaking.
# Reader-only: this never touches dictation output, and these spellings are
# deliberately NOT in BASE_VOCABULARY (that list feeds Whisper's decoder hint and
# the casing pass, where a phonetic spelling would do damage).
PRONUNCIATION_MAP = {
    "Yuki": "Yoo-kee",
    "aqeeq": "ah-keek",
    "Type-Moon": "Type Moon",
    "Nasu": "Nah-soo",
    "Tsukihime": "Soo-kee-hee-may",
}

# Trailing spoken punctuation → the real mark. Whisper punctuates what it hears, so
# "that is all period" usually arrives as "That is all, period." — apply_macros drops
# Whisper's closing mark before matching, and _SPOKEN swallows the one in front.
_SPOKEN = r'[\s,.;:!?،؛؟]+'
PUNCTUATION_MAP = {
    r'(?i)' + _SPOKEN + r'(period|full stop)$': '.',
    _SPOKEN + r'نقطة$': '.',
    r'(?i)' + _SPOKEN + r'comma$': ',',
    _SPOKEN + r'فاصلة$': '،',
    r'(?i)' + _SPOKEN + r'(question mark)$': '?',
    _SPOKEN + r'علامة استفهام$': '؟'
}