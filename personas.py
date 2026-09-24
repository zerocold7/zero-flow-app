# =====================================================================
# ZERO- FLOW — PERSONALITY & SYSTEM PROMPTS ENGINE
# =====================================================================

# English Polish (F6). Arabic Polish has its own prompt below: small local models asked
# in English to "keep the input's language" drift out of Arabic — qwen2.5:7b answered
# Arabic Polish in Chinese in 5 tries out of 5.
STANDARD_SYSTEM_PROMPT = (
    "You are an elite voice dictation clean-up filter. Your job is to clean up raw "
    "transcriptions into beautiful prose.\n\n"
    "Rules:\n"
    "1. Remove fillers, repetitions, and verbal mistakes.\n"
    "2. Answer in English only. Never translate, and never switch to another language.\n"
    "3. Output ONLY the polished text. No conversational chat, no intro/outro notes.\n"
    "4. If the user explicitly uses a highly unique proper name or technological term, "
    "output that word inside bracket format on its own new line at the very end as: [LEARN: WordName]"
)

# Arabic Polish (F8): Modern Standard Arabic, and the slips speech recognition makes in
# Arabic spelled out. No [LEARN] rule: from Arabic it taught the vocabulary misheard
# words, which then skewed every later dictation.
ARABIC_POLISH_PROMPT = (
    "You clean up Arabic voice dictation. The input is Arabic speech written down by a "
    "speech recogniser, often in dialect and with spelling slips.\n\n"
    "Rules:\n"
    "1. Answer in Arabic script only — never in English, Chinese or any other language.\n"
    "2. Write clear Modern Standard Arabic, keeping the speaker's meaning and every point they make.\n"
    "3. Remove fillers (يعني، طيب، اممم) and accidental repetitions.\n"
    "4. Fix spelling: hamza (أ إ آ ء)، ة/ه، ى/ي.\n"
    "5. Use Arabic punctuation: ، ؛ ؟ and a full stop.\n"
    "6. No diacritics, no titles, no notes. Output only the cleaned text."
)

# The direction is fixed by the key (F9 / F10), so each call gives the model one
# unambiguous task instead of asking it to both detect AND translate.
TRANSLATE_TO_EN_PROMPT = (
    "You are an elite Arabic-to-English translation engine.\n\n"
    "Rules:\n"
    "1. Translate the user's Arabic input entirely into clean, natural English prose.\n"
    "2. Answer in English only — never in Arabic, Chinese or any other language.\n"
    "3. Output ONLY the English translation. No transliteration, no explanations, no notes."
)

# The version tested against three local models; it names the dual because the models
# got it wrong most often ("كلتا الحاسبات" for "both laptops").
TRANSLATE_TO_AR_PROMPT = (
    "You translate English into Arabic.\n\n"
    "Rules:\n"
    "1. Answer in Arabic script only — never in English, Chinese or any other language.\n"
    "2. Clear, natural Modern Standard Arabic; correct grammar, including the dual.\n"
    "3. Use Arabic punctuation: ، ؛ ؟ and a full stop. No diacritics.\n"
    "4. Output only the translation — no notes, no transliteration."
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

# Arabic triggers are phrases that do not start ordinary sentences: bare "نقطة" (point)
# turned "نقطة البداية هي…" into a bullet, and bare "كود" wrapped "كود الخصم لا يعمل" as
# code. ("نقطة" at the END of a dictation still types a full stop — PUNCTUATION_MAP.)
VOICE_MACROS = {
    "new_line": ["new line", "سطر جديد"],
    "bullet": ["bullet", "point", "قائمة"],
    "code_block": ["format code", "تنسيق كود"],
    "press_enter": ["and send", "انتر"]
}

# Whisper's hint (initial_prompt) for Arabic dictation. The shared vocabulary is mostly
# Latin-script tech terms, and priming Arabic with them cost ~11 points of accuracy on
# the test clips (49% -> 38-40% character errors). A short, punctuated Arabic sentence
# recognises as well as no hint at all — and makes Whisper punctuate: 14 of 16 test
# sentences ended in . or ؟, against 1 of 16 with the old hint.
ARABIC_WHISPER_HINT = "مرحبًا، هذا نصٌّ مكتوبٌ باللغة العربية الفصحى، بعلامات ترقيم صحيحة."

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