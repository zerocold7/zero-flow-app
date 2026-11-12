"""Phase 7: can Whisper (CTranslate2) run on the CUDA libraries torch already ships, so
the GPU edition need not carry nvidia-cublas-cu12 and nvidia-cudnn-cu12 as well (1.9 GB)?

    venv\\Scripts\\python tools\\measure_cuda_from_torch.py

Adds only torch\\lib to the DLL search path (never the nvidia packages), loads the
configured Whisper model on CUDA, transcribes one second of silence and a real clip if
one is in tools/bench/clips, and prints which cuBLAS / cuDNN files were really loaded.
"""
import ctypes
import glob
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def loaded(name: str) -> str | None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p
    handle = kernel32.GetModuleHandleW(name)
    if not handle:
        return None
    buffer = ctypes.create_unicode_buffer(1024)
    kernel32.GetModuleFileNameW(ctypes.c_void_p(handle), buffer, 1024)
    return buffer.value


def main():
    import importlib.util
    torch_lib = os.path.join(os.path.dirname(importlib.util.find_spec("torch").origin), "lib")
    os.add_dll_directory(torch_lib)
    os.environ["PATH"] = torch_lib + os.pathsep + os.environ.get("PATH", "")
    import numpy as np
    from faster_whisper import WhisperModel
    from zeroflow import settings, stt
    path = stt.resolve_whisper_model()
    start = time.perf_counter()
    model = WhisperModel(path, device="cuda", compute_type=settings.WHISPER_COMPUTE_TYPE)
    list(model.transcribe(np.zeros(16000, dtype=np.float32), vad_filter=False)[0])
    print(f"loaded and warmed on CUDA in {time.perf_counter() - start:.1f} s")
    clips = sorted(glob.glob(os.path.join(ROOT, "tools", "bench", "clips", "*.wav")))
    if clips:
        import wave
        with wave.open(clips[0]) as w:
            audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        audio = audio.astype(np.float32) / 32768
        start = time.perf_counter()
        text = " ".join(s.text for s in model.transcribe(audio, beam_size=5)[0])
        print(f"clip {os.path.basename(clips[0])}: {time.perf_counter() - start:.2f} s: "
              f"{text.strip()[:80]}")
    for dll in ("cublas64_12.dll", "cublasLt64_12.dll", "cudnn64_9.dll",
                "cudnn_ops64_9.dll", "cudnn_cnn64_9.dll"):
        print(f"  {dll}: {loaded(dll)}")


if __name__ == "__main__":
    main()
