# Zero- Flow

A Windows desktop tool that moves words between voice and text in both directions, in English and Arabic, local by default.

## Language

### The product and its halves

**Zero- Flow**:
The product as a whole.
_Avoid_: Flow (alone), the engine, the app (when the product is meant)

**Engine**:
The one running program that hosts Dictation and the Reader. There is only ever one Engine.
_Avoid_: engine runner, supervisor (in user-facing text)

**Dictation**:
The half that turns speech into text typed where the cursor is.
_Avoid_: Flow, the flow half, writing, STT (in user-facing text)

**Reader**:
The half that reads the selected text aloud.
_Avoid_: TTS, voice engine (in user-facing text)

**Paused**:
The Engine's state when both Dictation and the Reader are switched off: it stays in the tray, holding no models and no keys.
_Avoid_: stopped, idle

### Languages

**Language pair**:
The two languages Dictation listens to and translates between. English + Arabic is the only pair today.
_Avoid_: languages (alone), locale

**Interface language**:
The language of the windows, menus and messages, chosen separately from the Language pair.
_Avoid_: UI locale, app language

### Keys

**Mode**:
What a record key does with the speech: Raw, Polish or Translate, in a given language.
_Avoid_: record mode names like `en_raw` (in user-facing text)

**Raw**:
A Mode that types the words exactly as spoken, with no AI.

**Polish**:
A Mode that has the AI clean grammar and fillers before typing.

**Translate**:
A Mode that has the AI turn the speech into the other language before typing.

**Action**:
A key that works on text that already exists, not on new speech: Tidy vocabulary, Clear history, Fix line.
_Avoid_: maintenance, purge, line fix

### What it keeps

**Dictation history**:
The saved list of past dictations, in full text, kept only while "Keep dictation history" is on.
_Avoid_: log, transcript log

**Debug log**:
The technical record of what the Engine did; it shows the size of dictated text, never the words, unless the user turns that on.
_Avoid_: history

**Learned vocabulary**:
The user's own list of words Dictation should spell correctly.
_Avoid_: dictionary, word list

### AI

**Provider**:
The service that answers AI requests: Built-in (the default), Ollama, or Custom.
_Avoid_: backend, LLM (as a noun for the service)

**Custom provider**:
Any AI service the user names by its address, model and key; Claude and other well-known services are presets of it.
_Avoid_: API provider, OpenAI provider

**Local provider**:
A provider that runs on this PC; no text leaves it. Built-in, Ollama, and a Custom provider whose address is this PC are local.

**Cloud provider**:
A provider on an outside server; picking one sends dictated text to that server.
_Avoid_: online AI, API mode
