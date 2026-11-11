"""The Interface language: the words of the windows, menus and messages.

A language is one table of {key: text}. To add a language, add a table to TABLES and its
code to settings INTERFACE_LANGUAGE; a key missing from a table shows its English text.
Arabic switches the layout to right-to-left (RTL).
"""
import ctypes

EN = {
    "app": "Zero- Flow",
    "tray.active": "Zero- Flow — active", "tray.paused": "Zero- Flow — paused",
    "tray.dictation": "Dictation on", "tray.reader": "Reader on",
    "tray.settings": "Settings…", "tray.unload": "Unload AI model",
    "tray.logs": "Open logs folder", "tray.exit": "Exit Engine", "tray.keys": "Keys",
    "keys.cancel": "Cancel recording / silence the Reader",
    "win.title": "Zero- Flow settings", "win.save": "Save", "win.cancel": "Cancel",
    "tab.general": "General", "tab.keys": "Keys", "tab.ai": "AI Provider",
    "tab.speech": "Speech and voice", "tab.advanced": "Advanced",
    "general.dictation": "Dictation on", "general.reader": "Reader on",
    "general.paused": "Both are off: Zero- Flow is Paused and holds no models and no keys.",
    "general.mic": "Microphone", "general.mic_default": "Windows default",
    "general.language": "Interface language", "general.pair": "Language pair",
    "general.pair_en_ar": "English + Arabic",
    "general.startup": "Start with Windows", "general.history": "Keep dictation history",
    "general.logwords": "Show dictated words in the log",
    "general.sounds": "Sounds", "general.notices": "Notifications",
    "general.clipboard": "Clipboard history never receives dictated text.",
    "lang.auto": "Follow Windows", "lang.en": "English", "lang.ar": "العربية",
    "keys.hint": "Click a box, then press the key.",
    "keys.raw_en": "Raw · English", "keys.polish_en": "Polish · English",
    "keys.raw_ar": "Raw · Arabic", "keys.polish_ar": "Polish · Arabic",
    "keys.en2ar": "Translate · English → Arabic", "keys.ar2en": "Translate · Arabic → English",
    "keys.fix": "Action · Fix line", "keys.maintenance": "Action · Tidy vocabulary",
    "keys.purge": "Action · Clear history", "keys.read": "Reader · Read the selection",
    "speech.whisper": "Speech model", "speech.device": "Speech device",
    "speech.voice": "Reader voice", "speech.speed": "Reader speed",
    "adv.restart": "Saving restarts Zero- Flow (about 5 seconds).",
    "adv.models": "Models folder", "adv.builtin": "Built-in AI model",
    "adv.smart": "Reader Smart mode", "adv.load_ai": "Load the AI at start",
    "saved.restart": "Saved. Restarting…", "saved.live": "Saved.",
    "problem.key": "The API key could not be saved: ",
}

AR = {
    "app": "زيرو فلو",
    "tray.active": "زيرو فلو — يعمل", "tray.paused": "زيرو فلو — متوقف مؤقتًا",
    "tray.dictation": "الإملاء يعمل", "tray.reader": "القارئ يعمل",
    "tray.settings": "الإعدادات…", "tray.unload": "إلغاء تحميل نموذج الذكاء",
    "tray.logs": "فتح مجلد السجلات", "tray.exit": "إنهاء المحرك", "tray.keys": "المفاتيح",
    "keys.cancel": "إلغاء التسجيل / إسكات القارئ",
    "win.title": "إعدادات زيرو فلو", "win.save": "حفظ", "win.cancel": "إلغاء",
    "tab.general": "عام", "tab.keys": "المفاتيح", "tab.ai": "مزود الذكاء",
    "tab.speech": "الصوت والكلام", "tab.advanced": "متقدم",
    "general.dictation": "الإملاء يعمل", "general.reader": "القارئ يعمل",
    "general.paused": "كلاهما متوقف: زيرو فلو في حالة إيقاف مؤقت ولا يحمّل نماذج أو مفاتيح.",
    "general.mic": "الميكروفون", "general.mic_default": "الافتراضي في ويندوز",
    "general.language": "لغة الواجهة", "general.pair": "زوج اللغات",
    "general.pair_en_ar": "الإنجليزية + العربية",
    "general.startup": "التشغيل مع ويندوز", "general.history": "حفظ سجل الإملاء",
    "general.logwords": "إظهار الكلمات المملاة في السجل",
    "general.sounds": "الأصوات", "general.notices": "الإشعارات",
    "general.clipboard": "سجل الحافظة لا يستقبل النص المملى أبدًا.",
    "lang.auto": "اتباع ويندوز", "lang.en": "English", "lang.ar": "العربية",
    "keys.hint": "اضغط على المربع ثم اضغط المفتاح.",
    "keys.raw_en": "حرفي · إنجليزي", "keys.polish_en": "تنقيح · إنجليزي",
    "keys.raw_ar": "حرفي · عربي", "keys.polish_ar": "تنقيح · عربي",
    "keys.en2ar": "ترجمة · إنجليزي ← عربي", "keys.ar2en": "ترجمة · عربي ← إنجليزي",
    "keys.fix": "إجراء · تصحيح السطر", "keys.maintenance": "إجراء · ترتيب المفردات",
    "keys.purge": "إجراء · مسح السجل", "keys.read": "القارئ · قراءة المحدد",
    "speech.whisper": "نموذج الكلام", "speech.device": "جهاز الكلام",
    "speech.voice": "صوت القارئ", "speech.speed": "سرعة القارئ",
    "adv.restart": "الحفظ يعيد تشغيل زيرو فلو (نحو 5 ثوانٍ).",
    "adv.models": "مجلد النماذج", "adv.builtin": "نموذج الذكاء المدمج",
    "adv.smart": "الوضع الذكي للقارئ", "adv.load_ai": "تحميل الذكاء عند التشغيل",
    "saved.restart": "تم الحفظ. إعادة التشغيل…", "saved.live": "تم الحفظ.",
    "problem.key": "تعذر حفظ مفتاح API: ",
}

TABLES = {"en": EN, "ar": AR}
RTL = {"ar"}
_current = "en"


def windows_language() -> str:
    """The two-letter code of Windows' display language, "en" if it has no table here."""
    try:
        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except Exception:
        return "en"
    primary = {0x09: "en", 0x01: "ar"}.get(langid & 0x3FF, "en")
    return primary if primary in TABLES else "en"


def choose(setting: str) -> str:
    """The language to use for INTERFACE_LANGUAGE ("auto", "en", "ar", …)."""
    global _current
    _current = windows_language() if setting == "auto" else (setting if setting in TABLES else "en")
    return _current


def current() -> str:
    return _current


def is_rtl() -> bool:
    return _current in RTL


def tr(key: str) -> str:
    return TABLES.get(_current, EN).get(key) or EN.get(key) or key
