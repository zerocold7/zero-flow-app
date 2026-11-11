# Arabic voice for the Reader: research (Phase 6)

Checked 2026-11-11. This is research only; nothing has been added to the code. The question: is there a **local** Arabic text-to-speech model whose licence allows **commercial use**? Kokoro, the Reader's English voice, has no Arabic.

## Answer

Yes. Two are worth measuring: **Chatterbox Multilingual** (MIT) and **SILMA TTS** (Apache-2.0 weights, MIT code). Both run locally and both name Arabic. Neither has been tried on this PC yet, so speed and quality are still unknown. The usual non-commercial choices (MMS, XTTS-v2, OuteTTS 1B) are ruled out by their licences.

## Candidates that allow commercial use

| Model | Licence (as the source states it) | Size | Arabic | Catches |
|---|---|---|---|---|
| **Chatterbox Multilingual** (Resemble AI), V3 | MIT ([model card][cb]) | ~0.5B | One of 23 languages | Every output carries Resemble's **Perth watermark**: inaudible, but it is there. Examples load it on `cuda`, and the card states no CPU figures. The card asks for a reference clip in the same language, or the accent leaks. There is no Arabic quality benchmark on the card. |
| **SILMA TTS v1** (SILMA AI) | Weights **Apache-2.0**, code **MIT** ([model card][silma]) | 150M | Arabic + English, built for both | Uses F5-TTS's architecture, but the card says it was **pretrained from scratch**, so F5-TTS's non-commercial weights are not inherited. It **needs a reference clip** (under 8 s) for its voice, and we would need the rights to that clip. RTF 0.12 on an RTX 4090; no CPU figures. Training data is "public and proprietary", with no data licence stated. Tashkeel (diacritics) is supported but not required. |
| **NAMAA Saudi TTS** | MIT ([model card][namaa]) | 536M | **Saudi dialect** | A fine-tune of Chatterbox, so it has the same watermark and needs. Of interest because the user writes in the Saudi dialect. Small project (1.7K downloads); the source of its training data was not checked. |
| **3arab-TTS 500M v2** | Apache-2.0 ([model card][3arab]) | 512M | MSA; dialects only partly | A one-person project with 2 likes. The training data source was not checked, so not recommended without that. |
| **Piper**, voice `ar_JO-kareem` | Voices repo: MIT ([piper-voices][piper]) | ~60 MB (ONNX) | Jordanian Arabic, one male voice | Small and fast on a CPU. However, the voice's **dataset licence is unknown**: the model card says "See URL", and that repo ([arabicttstrain][kareem]) shows no licence and no source for the audio. Piper phonemises with **espeak-ng (GPL-3)**, the same decision Phase 7 already has to make. The original `rhasspy/piper` is archived; its successor is GPL-3. |
| **Windows' own voices** (Hoda, Naayf) | Part of Windows | 0 (already installed) | Arabic, Saudi Arabic | Microsoft lists them for Narrator ([supported voices][ms]). Other apps reach them through the Windows speech API, so nothing is downloaded or bundled. Robotic next to the neural models. I found **no Microsoft text on third-party apps using them**: unverified. |

## Ruled out: non-commercial or not Arabic

- **MMS-TTS Arabic** (Meta, `facebook/mms-tts-ara`): CC-BY-NC-4.0 ([card][mms]).
- **XTTS-v2** (Coqui): licence "other", the Coqui Public Model Licence, which is non-commercial ([card][xtts]). Coqui has closed, so a commercial licence can no longer be bought.
- **OuteTTS 1.0 1B**: CC-BY-NC-SA-4.0 ([card][oute1b]). The 0.6B model is Apache-2.0 but **has no Arabic** ([card][oute06]).
- **Kokoro**: no Arabic voice.

## What it would take (for a later phase, if wanted)

1. **Measure before choosing**, as with Kokoro: cold load, time to first sound, and realtime factor on GPU and CPU. Listen to the same Arabic paragraph from Chatterbox, SILMA and NAMAA.
2. **Watermark:** decide whether a hidden Perth watermark in every Chatterbox read is acceptable for a product you sell.
3. **Reference voice:** Chatterbox and SILMA speak in the voice of a reference clip. The app would need a clip it has the rights to ship, recorded for the purpose or licensed.
4. **Language choice:** the Reader would have to tell Arabic text from English (a script check is enough) and pick the voice to match.
5. **Phase 7:** add the model's licence to the licence audit and `THIRD-PARTY-NOTICES.txt`. Models are fetched at first run, not bundled.

Licences above are as stated on each model card, read on the date above. Model cards can change, so read each `LICENSE` file again before shipping.

[cb]: https://huggingface.co/ResembleAI/chatterbox
[silma]: https://huggingface.co/silma-ai/silma-tts
[namaa]: https://huggingface.co/NAMAA-Space/NAMAA-Saudi-TTS
[3arab]: https://huggingface.co/sherif1313/3arab-TTS-500M-v2
[piper]: https://huggingface.co/rhasspy/piper-voices/blob/main/ar/ar_JO/kareem/medium/MODEL_CARD
[kareem]: https://github.com/AliMokhammad/arabicttstrain/
[ms]: https://support.microsoft.com/en-us/Accessibility/windows/narrator/appendix-a-supported-languages-and-voices
[mms]: https://huggingface.co/facebook/mms-tts-ara
[xtts]: https://huggingface.co/coqui/XTTS-v2
[oute1b]: https://huggingface.co/OuteAI/Llama-OuteTTS-1.0-1B
[oute06]: https://huggingface.co/OuteAI/OuteTTS-1.0-0.6B
