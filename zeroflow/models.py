"""The revision each model is downloaded at: a fixed commit on the Hugging Face Hub.

Without one, a fresh install takes whatever was uploaded last, so a changed or
tampered model would be downloaded and run — the reader's voice weights are loaded
with torch. Pinned like the llama.cpp build (llm/llama_runtime.BUILD). A model not
listed here (one you set yourself in .env) is taken at its latest revision.

To move a model to a newer upload: put its new commit here and check it, once.
"""

REVISIONS = {
    # Speech to text (faster-whisper), every name it knows plus the turbo build.
    "Systran/faster-whisper-tiny": "d90ca5fe260221311c53c58e660288d3deb8d356",
    "Systran/faster-whisper-tiny.en": "0d3d19a32d3338f10357c0889762bd8d64bbdeba",
    "Systran/faster-whisper-base": "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66",
    "Systran/faster-whisper-base.en": "3d3d5dee26484f91867d81cb899cfcf72b96be6c",
    "Systran/faster-whisper-small": "536b0662742c02347bc0e980a01041f333bce120",
    "Systran/faster-whisper-small.en": "d1d751a5f8271d482d14ca55d9e2deeebbae577f",
    "Systran/faster-whisper-medium": "08e178d48790749d25932bbc082711ddcfdfbc4f",
    "Systran/faster-whisper-medium.en": "a29b04bd15381511a9af671baec01072039215e3",
    "Systran/faster-whisper-large-v1": "b07c8d4be0be90092aa01a29c975077acb8d15c9",
    "Systran/faster-whisper-large-v2": "f0fe81560cb8b68660e564f55dd99207059c092e",
    "Systran/faster-whisper-large-v3": "edaa852ec7e145841d8ffdb056a99866b5f0a478",
    "Systran/faster-distil-whisper-small.en": "ef77d90526ccd62cde3808ee70626a01e5cf83e4",
    "Systran/faster-distil-whisper-medium.en": "80ddfce281f77766d8943d63109199fc8145dfa5",
    "Systran/faster-distil-whisper-large-v2": "fe9b404fc56de3f7c38606ef9ba6fd83526d05e4",
    "Systran/faster-distil-whisper-large-v3": "c3058b475261292e64a0412df1d2681c06260fab",
    "mobiuslabsgmbh/faster-whisper-large-v3-turbo": "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf",
    # The built-in AI (Gemma 4, GGUF).
    "google/gemma-4-E4B-it-qat-q4_0-gguf": "4b4a2c1d584be7264f87aac328a1bc739ce81b6c",
    "google/gemma-4-E2B-it-qat-q4_0-gguf": "675cff42a74c774d6cb76f76d8eacb49b48c9b93",
    # The reader's voice.
    "hexgrad/Kokoro-82M": "f3ff3571791e39611d31c381e3a41a3af07b4987",
}


def revision(repo: str) -> str | None:
    """The pinned commit of `repo`, or None (its latest) for a model not listed."""
    return REVISIONS.get(repo)
