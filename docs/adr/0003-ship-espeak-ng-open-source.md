# The installer ships espeak-ng, so Zero- Flow is published as open source

The Reader keeps espeak-ng (GPL-3.0-or-later) and phonemizer-fork (GPL-3.0-or-later), which pronounce the words outside Kokoro's English dictionary: 2.9% of the words in the project's own docs (tools/measure_espeak_use.py, 2026-11-12), names and technical terms among them. Without them kokoro skips those words, so the Reader would silently leave words out. Because the installer carries GPL-3 code that runs in the Reader's process, the installer as a whole is distributed under GPL-3: the complete source must be available to everyone who receives it, and a closed-source 2.x is ruled out. Zero- Flow's own code may stay MIT, which is GPL-3-compatible; the licence choice in Phase 8 must stay compatible with GPL-3.

Rejected: dropping espeak (words skipped); a permissive replacement such as g2p_en (unmeasured quality, real work); downloading espeak at first run to keep it out of the installer (it still runs in-process, a legal grey area).

PyAV's FFmpeg, also GPL in its bundled build (x264, x265, postproc), is a separate case: Zero- Flow never decodes audio files, so the build replaces `av` and ships none of it.
