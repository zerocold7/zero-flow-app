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
    "speech.output": "Reader output",
    "adv.restart": "Saving restarts Zero- Flow (about 5 seconds).",
    "adv.models": "Models folder", "adv.builtin": "Built-in AI model",
    "adv.smart": "Reader Smart mode", "adv.load_ai": "Load the AI at start",
    "saved.restart": "Saved. Restarting…", "saved.live": "Saved.",
    "problem.key": "The API key could not be saved: ",
    "general.setup_again": "Run setup again…",
    "wiz.title": "Set up Zero- Flow", "wiz.next": "Next", "wiz.back": "Back",
    "wiz.finish": "Finish",
    "wiz.welcome": "Welcome",
    "wiz.welcome_text": "Zero- Flow types what you say where the cursor is, and reads "
                        "selected text aloud, in English and Arabic. This takes a few "
                        "minutes, most of it downloading the models once.",
    "wiz.this_pc": "This PC", "wiz.cpu": "Processor", "wiz.ram": "Memory",
    "wiz.card": "Graphics card", "wiz.no_card": "none", "wiz.kind": "Best set-up",
    "wiz.this_pc_hint": "Chosen for this PC. A smaller speech model is faster and less accurate.",
    "wiz.models_text": "The speech, voice and AI models are downloaded once into this folder.",
    "wiz.space": "Needs {need}; {free} free.",
    "wiz.space_short": "Not enough space: choose another folder.",
    "wiz.ai_text": "Built-in runs on this PC and needs no account. Polish and Translate use it.",
    "wiz.downloads": "Downloads",
    "wiz.downloads_text": "Each model is downloaded once. You can cancel and try again.",
    "wiz.cancel_download": "Cancel download", "wiz.retry": "Try again",
    "wiz.speed": "{speed} Mbit/s, about {minutes} min left",
    "wiz.download_failed": "A download failed and was removed: ",
    "wiz.download_cancelled": "Cancelled. Nothing half-downloaded was kept.",
    "wiz.downloads_done": "Everything is downloaded.",
    "wiz.mic_text": "Choose the microphone, press Test and say a few words.",
    "wiz.mic_test": "Test the microphone (3 s)",
    "wiz.ai_test_title": "AI test",
    "wiz.ai_test_text": "Sends one short sentence to the AI. The built-in AI takes up to a "
                        "minute to load the first time.",
    "wiz.ai_test": "Test the AI",
    "wiz.pass": "Passed", "wiz.fail": "Failed",
    "wiz.done": "Ready",
    "wiz.done_text": "Press Finish: Zero- Flow restarts in about 5 seconds. Then click where "
                     "you want to type, hold a key and speak:",
    "tray.history": "Dictation history…", "tray.vocabulary": "Learned vocabulary…",
    "tray.diagnostics": "Copy diagnostics",
    "hist.title": "Dictation history", "hist.search": "Search",
    "hist.copy": "Copy", "hist.delete": "Delete", "hist.clear": "Clear all",
    "hist.copied": "Copied.",
    "hist.clear_ask": "Delete the whole Dictation history? This cannot be undone.",
    "hist.off": "\"Keep dictation history\" is off: new dictations are not saved. "
                "Turn it on in Settings.",
    "vocab.title": "Learned vocabulary",
    "vocab.hint": "Names and terms Dictation should spell correctly. Changes apply to the "
                  "next dictation.",
    "vocab.add": "Add", "vocab.change": "Change", "vocab.delete": "Delete",
    "vocab.tidy": "Tidy vocabulary", "vocab.saved": "Saved.",
    "vocab.blank": "Type a word first.", "vocab.repeated": "That word is in the list already.",
    "vocab.long": "A term is a name or a short phrase, at most 4 words.",
    "vocab.tidy_running": "The AI is tidying the list…", "vocab.tidy_done": "Tidy finished.",
    "vocab.tidy_failed": "Tidy failed: ",
    "diag.copied": "Diagnostics copied. They hold no dictated words and no keys.",
    "diag.failed": "Diagnostics could not be copied: ",
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
    "speech.output": "مخرج صوت القارئ",
    "adv.restart": "الحفظ يعيد تشغيل زيرو فلو (نحو 5 ثوانٍ).",
    "adv.models": "مجلد النماذج", "adv.builtin": "نموذج الذكاء المدمج",
    "adv.smart": "الوضع الذكي للقارئ", "adv.load_ai": "تحميل الذكاء عند التشغيل",
    "saved.restart": "تم الحفظ. إعادة التشغيل…", "saved.live": "تم الحفظ.",
    "problem.key": "تعذر حفظ مفتاح API: ",
    "general.setup_again": "إعادة الإعداد…",
    "wiz.title": "إعداد زيرو فلو", "wiz.next": "التالي", "wiz.back": "السابق",
    "wiz.finish": "إنهاء",
    "wiz.welcome": "مرحبًا",
    "wiz.welcome_text": "زيرو فلو يكتب ما تقوله حيث يوجد المؤشر، ويقرأ النص المحدد بصوت "
                        "عالٍ، بالإنجليزية والعربية. يستغرق الإعداد بضع دقائق، معظمها "
                        "لتنزيل النماذج مرة واحدة.",
    "wiz.this_pc": "هذا الجهاز", "wiz.cpu": "المعالج", "wiz.ram": "الذاكرة",
    "wiz.card": "بطاقة الرسومات", "wiz.no_card": "لا يوجد", "wiz.kind": "الإعداد الأنسب",
    "wiz.this_pc_hint": "تم الاختيار لهذا الجهاز. نموذج الكلام الأصغر أسرع وأقل دقة.",
    "wiz.models_text": "تُنزَّل نماذج الكلام والصوت والذكاء مرة واحدة في هذا المجلد.",
    "wiz.space": "يحتاج {need}؛ المتاح {free}.",
    "wiz.space_short": "المساحة غير كافية: اختر مجلدًا آخر.",
    "wiz.ai_text": "المدمج يعمل على هذا الجهاز ولا يحتاج حسابًا. يستخدمه التنقيح والترجمة.",
    "wiz.downloads": "التنزيلات",
    "wiz.downloads_text": "يُنزَّل كل نموذج مرة واحدة. يمكنك الإلغاء والمحاولة مجددًا.",
    "wiz.cancel_download": "إلغاء التنزيل", "wiz.retry": "المحاولة مجددًا",
    "wiz.speed": "{speed} ميغابت/ث، يتبقى نحو {minutes} دقيقة",
    "wiz.download_failed": "فشل تنزيل وتمت إزالته: ",
    "wiz.download_cancelled": "تم الإلغاء. لم يُحتفظ بأي تنزيل ناقص.",
    "wiz.downloads_done": "تم تنزيل كل شيء.",
    "wiz.mic_text": "اختر الميكروفون، واضغط اختبار وقل بضع كلمات.",
    "wiz.mic_test": "اختبار الميكروفون (3 ثوانٍ)",
    "wiz.ai_test_title": "اختبار الذكاء",
    "wiz.ai_test_text": "يرسل جملة قصيرة واحدة إلى الذكاء. يحتاج الذكاء المدمج حتى دقيقة "
                        "للتحميل في المرة الأولى.",
    "wiz.ai_test": "اختبار الذكاء",
    "wiz.pass": "نجح", "wiz.fail": "فشل",
    "wiz.done": "جاهز",
    "wiz.done_text": "اضغط إنهاء: يُعاد تشغيل زيرو فلو خلال نحو 5 ثوانٍ. ثم انقر حيث تريد "
                     "الكتابة، واضغط مفتاحًا وتحدّث:",
    "tray.history": "سجل الإملاء…", "tray.vocabulary": "المفردات المحفوظة…",
    "tray.diagnostics": "نسخ معلومات التشخيص",
    "hist.title": "سجل الإملاء", "hist.search": "بحث",
    "hist.copy": "نسخ", "hist.delete": "حذف", "hist.clear": "مسح الكل",
    "hist.copied": "تم النسخ.",
    "hist.clear_ask": "حذف سجل الإملاء كله؟ لا يمكن التراجع عن ذلك.",
    "hist.off": "خيار \"حفظ سجل الإملاء\" متوقف: لا يُحفظ الإملاء الجديد. فعّله من الإعدادات.",
    "vocab.title": "المفردات المحفوظة",
    "vocab.hint": "أسماء ومصطلحات يجب أن يكتبها الإملاء بشكل صحيح. تُطبَّق التغييرات على "
                  "الإملاء التالي.",
    "vocab.add": "إضافة", "vocab.change": "تعديل", "vocab.delete": "حذف",
    "vocab.tidy": "ترتيب المفردات", "vocab.saved": "تم الحفظ.",
    "vocab.blank": "اكتب كلمة أولًا.", "vocab.repeated": "هذه الكلمة موجودة في القائمة.",
    "vocab.long": "المصطلح اسم أو عبارة قصيرة، 4 كلمات على الأكثر.",
    "vocab.tidy_running": "الذكاء يرتب القائمة…", "vocab.tidy_done": "انتهى الترتيب.",
    "vocab.tidy_failed": "فشل الترتيب: ",
    "diag.copied": "تم نسخ معلومات التشخيص. لا تحتوي على كلمات مملاة ولا مفاتيح.",
    "diag.failed": "تعذر نسخ معلومات التشخيص: ",
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
