<div dir="rtl">

# دليل التثبيت

> 🌍 In English: [Install Guide](INSTALL.md) · 🟢 **لم تثبّت شيئاً كهذا من قبل؟**
> [الدليل المبسّط للمبتدئين](SETUP-CPU-LAPTOP.ar.md) يشرح كل خطوة على لابتوب بلا كرت شاشة.

طريق واحد لكل الأجهزة. الخطوة الوحيدة التي تختلف حسب العتاد هي **الخطوة الرابعة** — والأداة `check_hardware.py` تخبرك أيّ نسخة منها تناسبك.

---

## ما تحتاجه
- **ويندوز 10 أو 11، نسخة 64-بت.** (ماك ولينكس غير مدعومين.)
- **حوالي 10 جيجابايت مساحة فارغة** للبرامج والنماذج (أقل في الأجهزة الأضعف).
- **ميكروفون** — المدمج يكفي — وسمّاعات لصوت القراءة.
- **الإنترنت أثناء التثبيت فقط.** بعد تحميل النماذج يعمل المحرك دون إنترنت.

---

## 1. ثبّت Python و Git و Ollama
افتح **PowerShell** (ابدأ ← اكتب *PowerShell*) ونفّذ الأوامر سطراً سطراً:

```powershell
winget install Python.Python.3.12
winget install Git.Git
winget install Ollama.Ollama
```

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

دوّن **فئة جهازك** (tier) و**نموذج الذكاء** الذي يسمّيه — الخطوتان 4 و 6 تعتمدان عليهما. شرح كل فئة في [دليل العتاد والضبط](HARDWARE.ar.md).

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
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

وحافظ على تحديث تعريف كرت NVIDIA.

**فئتا `cpu-only` و `amd-intel-gpu`** — تجاوز مكتبات NVIDIA (1.2 جيجابايت). هذا الأمر يثبّت كل ما في `requirements.txt` ما عدا سطرَي `nvidia-`:

```powershell
.\venv\Scripts\python.exe -m pip install ((Get-Content requirements.txt) | Where-Object { $_ -match '^[A-Za-z]' -and $_ -notmatch '^nvidia-' })
```

هذه الخطوة تستغرق عدة دقائق.

## 5. اكتب إعداداتك

```powershell
python check_hardware.py --apply
```

ينشئ هذا الأمر ملف `.env` بإعدادات فئتك (وإن كان لديك `.env` مسبقاً يعدّل تلك الأسطر فقط ويحفظ النسخة القديمة باسم `.env.bak`). بقية الإعدادات — الأزرار والصوت والتنبيهات — مشروحة في [CONFIGURATION.md](../CONFIGURATION.md).

## 6. حمّل نموذج الذكاء
يعمل Ollama في الخلفية بعد تثبيته (أيقونته بجانب الساعة). حمّل النموذج الذي سمّاه الفحص، مثلاً:

```powershell
ollama pull qwen2.5:3b
```

شغّل `python check_hardware.py` مرة أخرى — كل سطر تحت *Checks* يجب أن يبدأ بـ `[ok]`.

## 7. شغّل المحرك
اضغط مرتين على **`Launch_Zero.bat`** داخل مجلد المشروع. (إن ظهرت رسالة *«Windows protected your PC»* اضغط **More info ← Run anyway**.)

**أول** تشغيل يحمّل نموذج الكلام والصوت — من 150 ميجابايت إلى 3 جيجابايت حسب فئتك. بعدها يُحمَّل كل شيء من جهازك.

- **الإملاء جاهز** عندما تظهر في النافذة المربع `Z E R O -   F L O W   E N G I N E`. سطر *Speech to text* فيه يخبرك أين حُمّل النموذج، مثل `[Whisper small · CPU · int8]`.
- **القراءة الصوتية جاهزة** عندما يظهر السطر `🔵 [TTS] Voice model ready.`

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
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

(في فئتَي `cpu-only` و `amd-intel-gpu` استخدم أمر الخطوة 4 بدل السطر الأخير.) التحديث لا يمسّ أبداً ملف `.env` ولا المفردات ولا السجل. أعد تشغيل `python check_hardware.py` لترى إن تغيّرت التوصيات.

## الإزالة
1. أغلق المحرك (أيقونته ← **Exit Engine**) واحذف المجلد `C:\local-voice-flow`.
2. النماذج المحمّلة: احذف المجلدات `models--Systran--faster-whisper-*` و `models--hexgrad--Kokoro-82M` داخل `%USERPROFILE%\.cache\huggingface\hub`.
3. نموذج الذكاء: `ollama rm qwen2.5:3b` (أو الذي حمّلته). ويُزال Python و Git و Ollama من *الإعدادات ← التطبيقات*.

---

هل هناك مشكلة؟ [دليل العتاد والضبط](HARDWARE.ar.md) لمشكلات السرعة، و[الأسئلة الشائعة (بالإنجليزية)](FAQ.md) لغيرها، وملفا السجل — `flow_debug.log` و `reader_debug.log` في مجلد المشروع — لمعرفة ما حدث فعلاً.

</div>
