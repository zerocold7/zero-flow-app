<div dir="rtl">

# دليل التثبيت

> 🌍 In English: [Install Guide](INSTALL.md) · 🟢 **لم تثبّت شيئاً كهذا من قبل؟**
> [الدليل المبسّط للمبتدئين](SETUP-CPU-LAPTOP.ar.md) يشرح كل خطوة على لابتوب بلا كرت شاشة.

طريق واحد لكل الأجهزة. الخطوة الوحيدة التي تختلف حسب العتاد هي **الخطوة الرابعة** — والأداة `check_hardware.py` تخبرك أيّ نسخة منها تناسبك.

---

## ما تحتاجه
- **ويندوز 10 أو 11، نسخة 64-بت.** (ماك ولينكس غير مدعومين.)
- **حوالي 15 جيجابايت مساحة فارغة** للبرامج والنماذج (أقل في الأجهزة الأضعف) — نموذج الذكاء وحده 5.15 جيجابايت.
- **ميكروفون** — المدمج يكفي — وسمّاعات لصوت القراءة.
- **الإنترنت أثناء التثبيت فقط.** بعد تحميل النماذج يعمل المحرك دون إنترنت.

---

## 1. ثبّت Python و Git
افتح **PowerShell** (ابدأ ← اكتب *PowerShell*) ونفّذ الأوامر سطراً سطراً:

```powershell
winget install Python.Python.3.12
winget install Git.Git
```

هذا كل ما تثبّته بيدك: نموذج الذكاء يعمل **مدمجاً في المحرك** (الخطوة 6)، فلا حاجة إلى Ollama.

أغلق PowerShell وافتحه من جديد، ثم تحقّق: الأمر `python --version` يجب أن يطبع `Python 3.12.x`. (بايثون 3.12 هي النسخة المُختبَرة.)

> **الميكروفون:** الإعدادات ← الخصوصية والأمان ← الميكروفون ← فعّل *الوصول إلى الميكروفون* و*السماح لتطبيقات سطح المكتب بالوصول إلى الميكروفون*. بدونها يسجّل المحرك صمتاً.

## 2. حمّل المشروع
أبعِده عن مجلدات OneDrive (سطح المكتب والمستندات) — ضعه على القرص `C:\`:

```powershell
cd C:\
git clone https://github.com/zerocold7/local-voice-flow.git
cd local-voice-flow
```

## 3. افحص جهازك

```powershell
python check_hardware.py
```

دوّن **فئة جهازك** (tier) — الخطوة 4 تعتمد عليها. شرح كل فئة في [دليل العتاد والضبط](HARDWARE.ar.md).

## 4. ثبّت مكتبات بايثون
أنشئ أولاً بيئة خاصة بالمحرك — كل ملفات التشغيل تستخدمها تلقائياً:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
```

ثم النسخة المناسبة لفئتك:

**فئات NVIDIA** (`nvidia-desktop` و `nvidia-laptop`) — ثبّت نسخة torch الخاصة بكرت الشاشة **أولاً**، وإلا يختار pip بصمت نسخة المعالج فيعمل الصوت على المعالج:

```powershell
.\venv\Scripts\python.exe -m pip install torch==2.5.1+cu121 --index-url https://download.pytorch.org/whl/cu121
.\venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints.txt
```

وحافظ على تحديث تعريف كرت NVIDIA.

**فئتا `cpu-only` و `amd-intel-gpu`** — تجاوز مكتبات NVIDIA (1.2 جيجابايت). هذا الأمر يثبّت كل ما في `requirements.txt` ما عدا سطرَي `nvidia-`:

```powershell
.\venv\Scripts\python.exe -m pip install ((Get-Content requirements.txt) | Where-Object { $_ -match '^[A-Za-z]' -and $_ -notmatch '^nvidia-' }) -c constraints.txt
```

هذه الخطوة تستغرق عدة دقائق.

## 5. اكتب إعداداتك

```powershell
python check_hardware.py --apply
```

ينشئ هذا الأمر ملف `.env` بإعدادات فئتك (وإن كان لديك `.env` مسبقاً يعدّل تلك الأسطر فقط ويحفظ النسخة القديمة باسم `.env.bak`). بقية الإعدادات — الأزرار والصوت والتنبيهات — مشروحة في [CONFIGURATION.md](../CONFIGURATION.md).

## 6. ثبّت الذكاء المدمج
التلميع والترجمة وبقية أزرار الذكاء تشغّل نموذج ذكاء على خادم `llama-server` من llama.cpp، والمحرك يشغّله ويوقفه بنفسه. ثبّته مرة واحدة:

```powershell
.\venv\Scripts\python.exe tools\get_llama.py
```

يختار الأمر النسخة التي يحتاجها جهازك، ويحمّل إصدار llama.cpp المثبَّت (البناء `b11619`) من GitHub ‏([github.com/ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp))، ويتحقق من كل ملف مضغوط مقابل بصمة SHA-256 المنشورة له، ثم يفكّه في `runtime\llama\<build>\`:

| النسخة | لمن | حجم التحميل |
|---|---|---|
| `cuda` | كروت NVIDIA | 625 MB |
| `vulkan` | كروت AMD Radeon / Intel Arc (لم تُختبر بعد) | 31 MB |
| `cpu` | كل ما عدا ذلك | 19 MB |

لاختيار النسخة بنفسك: `--variant cuda` أو `--variant vulkan` أو `--variant cpu`.

أما **نموذج الذكاء** نفسه فيُحمَّل تلقائياً عند أول تشغيل للمحرك — بلا حساب ولا أمر تحميل: نموذج **Gemma 4 E4B** من Google ‏(5.15 جيجابايت، رخصة Apache 2.0). على كرت NVIDIA في لابتوب بذاكرة 4–5 جيجابايت، أو مع رام 8 جيجابايت أو أقل، تكون الخطوة 5 قد اختارت بدلاً منه النموذج الأصغر **Gemma 4 E2B** ‏(3.35 جيجابايت)؛ وجودة عربيّته لم تُختبر بعد.

شغّل `python check_hardware.py` مرة أخرى — كل سطر تحت *Checks* يجب أن يبدأ بـ `[ok]`.

> **تفضّل Ollama أو خدمة ذكاء سحابية؟** غيّر `AI_PROVIDER` في ملف `.env` — انظر [CONFIGURATION.md §6](../CONFIGURATION.md#6-choosing-the-ai-provider). وإن لم يكن الذكاء المدمج مثبّتاً، يقول المحرك ذلك عند التشغيل (في النافذة والسجل وإشعار منبثق يذكر `tools/get_llama.py`) ويستخدم Ollama بدلاً منه.

## 7. شغّل المحرك
اضغط مرتين على **`Launch_Zero.bat`** داخل مجلد المشروع. (إن ظهرت رسالة *«Windows protected your PC»* اضغط **More info ← Run anyway**.)

**أول** تشغيل يحمّل نموذج الكلام والصوت — من 150 ميجابايت إلى 3 جيجابايت حسب فئتك — ونموذج الذكاء (5.15 جيجابايت، أو 3.35 جيجابايت لـ Gemma 4 E2B). بعدها يُحمَّل كل شيء من جهازك.

- **الإملاء جاهز** عندما تظهر في النافذة المربع `Z E R O -   F L O W   E N G I N E`. سطر *Speech to text* فيه يخبرك أين حُمّل النموذج، مثل `[Whisper small · CPU · int8]`.
- **القراءة الصوتية جاهزة** عندما يظهر السطر `🔵 [TTS] Voice model ready.`
- سطر *AI model* في المربع نفسه يسمّي نموذج الذكاء، مثل `Gemma 4 E4B · built in (cuda)`.

## 8. جرّبه
1. اضغط داخل المفكرة. اضغط **`F7`** مرة، قل جملة بالعربية، ثم اضغط **`F7`** مرة أخرى. يظهر كلامك بعد لحظة. (`F5` للإنجليزية.) *اضغط الزر ولا تُمسكه.*
2. ظلِّل النص واضغط **`F4`** — يقرؤه الصوت. **`Esc`** يوقفه.

أزرار F في اللابتوب تغيّر الصوت بدل ذلك؟ اضغط **`Fn + Esc`** (قفل Fn) أو أمسك `Fn` مع الزر. القائمة الكاملة للأزرار والأوامر الصوتية في [README](../README.md).

---

## التشغيل تلقائياً مع ويندوز
اضغط `Win + R` واكتب `shell:startup` ثم Enter. في المجلد الذي يُفتح: زر أيمن ← *جديد ← اختصار* ← اختر `Launch_Zero_Silent.vbs`. سيعمل المحرك مخفياً عند كل تسجيل دخول؛ أوقفه من أيقونته (**Exit Engine**).

## التحديث

```powershell
cd C:\local-voice-flow
git pull
.\venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints.txt
```

(في فئتَي `cpu-only` و `amd-intel-gpu` استخدم أمر الخطوة 4 بدل السطر الأخير.) تحدّث من نسخة كانت تستخدم Ollama؟ نفّذ أيضاً الخطوة 6 (`.\venv\Scripts\python.exe tools\get_llama.py`) — وإلى أن تفعل يبقى المحرك على Ollama ويقول ذلك عند التشغيل. التحديث لا يمسّ أبداً ملف `.env` ولا المفردات ولا السجل. أعد تشغيل `python check_hardware.py` لترى إن تغيّرت التوصيات.

## الإزالة
1. أغلق المحرك (أيقونته ← **Exit Engine**) واحذف المجلد `C:\local-voice-flow` — ويُحذف معه مجلد `runtime\` الخاص بالذكاء المدمج.
2. النماذج المحمّلة: احذف المجلدات `models--Systran--faster-whisper-*` و `models--hexgrad--Kokoro-82M` و `models--google--gemma-4-E4B-it-qat-q4_0-gguf` (أو `…-E2B-…`) داخل `%USERPROFILE%\.cache\huggingface\hub`.
3. يُزال Python و Git من *الإعدادات ← التطبيقات*. وإن كنت استخدمت Ollama أيضاً، احذف نموذجه أولاً (`ollama rm <الاسم>`) ثم أزِل Ollama نفسه بالطريقة ذاتها.

---

هل هناك مشكلة؟ [دليل العتاد والضبط](HARDWARE.ar.md) لمشكلات السرعة، و[الأسئلة الشائعة (بالإنجليزية)](FAQ.md) لغيرها، وملفا السجل — `flow_debug.log` و `reader_debug.log` في مجلد المشروع — لمعرفة ما حدث فعلاً.

</div>
