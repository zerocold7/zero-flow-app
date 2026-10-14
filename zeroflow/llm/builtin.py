"""The built-in AI: llama.cpp's llama-server, run by the engine itself as a hidden child
process, with Google's Gemma 4 E4B — no Ollama to install.

Measured on an RTX 4070 against Ollama with the same model family: loads in 3.1 s (Ollama
6.8-7.1 s), answers a Polish in 0.26 s (0.37 s), the same English and Arabic, ~3.2 GB of
graphics memory. With Whisper and the reader's voice, 9.3 GB of the card's 12.3 GB.

The server listens on a fixed local port (AI_BUILTIN_PORT, this PC only). Whoever needs it
first starts it; anyone else — the reader is a separate process — finds it running and
uses it, so the model is never loaded twice. Started by the engine, it is tied to the
engine's lifetime (a Job Object, see zeroflow.signals), so it never outlives it.
"""
import logging
import os
import subprocess
import threading
import time

import requests

from zeroflow import signals, ui
from zeroflow.llm import llama_runtime, openai_compatible
from zeroflow.paths import log_dir
from zeroflow.settings import (AI_BUILTIN_FILE, AI_BUILTIN_PORT, AI_BUILTIN_REPO, AI_NUM_CTX,
                               ENABLE_TOASTS)

# How long a start may take before giving up: loading the model from disk takes ~3 s on
# a graphics card and longer on a CPU or a slow disk. (The first ever start downloads the
# model before this clock begins.)
START_TIMEOUT = 120
CREATE_NO_WINDOW = 0x08000000

_lock = threading.Lock()
_process = None           # the llama-server this process started, if any


class BuiltinUnavailable(Exception):
    """The built-in AI cannot run here; the message says why and how to fix it."""


def _variant() -> str:
    return llama_runtime.chosen_variant()


def available() -> bool:
    """True if the runtime this PC needs is installed (tools/get_llama.py)."""
    return llama_runtime.installed(_variant())


def _launcher(variant: str) -> list[str]:
    if not llama_runtime.installed(variant):
        raise BuiltinUnavailable(f"the built-in AI's {variant} runtime is not installed — "
                                 f"run tools/get_llama.py")
    return [llama_runtime.server_path(variant)]


def _model_path() -> str:
    """The model file from the local model cache; downloaded once, the first time."""
    from huggingface_hub import hf_hub_download
    try:
        return hf_hub_download(AI_BUILTIN_REPO, AI_BUILTIN_FILE, local_files_only=True)
    except Exception:
        print(f"{ui.C_ACCENT}⬇️  Downloading the AI model {AI_BUILTIN_FILE} "
              f"(5 GB, first run only)...{ui.C_RESET}")
        logging.info(f"Downloading the built-in AI model {AI_BUILTIN_REPO}/{AI_BUILTIN_FILE}.")
        return hf_hub_download(AI_BUILTIN_REPO, AI_BUILTIN_FILE)


def _url(path: str) -> str:
    return f"http://127.0.0.1:{AI_BUILTIN_PORT}{path}"


def _healthy() -> bool:
    try:
        return requests.get(_url("/health"), timeout=1).status_code == 200
    except requests.RequestException:
        return False


def start() -> bool:
    """Make sure a server is answering — ours, or one already running. False (with the
    reason logged and shown) if it cannot be."""
    global _process
    with _lock:
        if _healthy():
            return True
        if _process is not None and _process.poll() is not None:
            logging.warning(f"The built-in AI stopped (code {_process.returncode}); "
                            f"restarting it.")
        try:
            variant = _variant()
            command = _launcher(variant) + [
                "-m", _model_path(),
                "-ngl", "0" if variant == "cpu" else "99",   # every layer on the card, or none
                "-c", str(AI_NUM_CTX),
                "-np", "1",                       # one request at a time: dictation is serial
                "--reasoning", "off",             # thinking made Polish 2.4-7.8 s, not 0.26 s
                "--host", "127.0.0.1",            # this PC only
                "--port", str(AI_BUILTIN_PORT),
            ]
        except Exception as e:
            return _unavailable(e)
        log = open(os.path.join(log_dir(), "builtin_ai.log"), "a", encoding="utf-8")
        try:
            _process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                        creationflags=CREATE_NO_WINDOW)
        except OSError as e:
            return _unavailable(e)
        finally:
            log.close()                           # the child holds its own handle
        signals.bind_child_to_this_process(_process)
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            if _process.poll() is not None:
                return _unavailable(f"llama-server stopped while starting (code "
                                    f"{_process.returncode}); see builtin_ai.log")
            if _healthy():
                logging.info(f"Built-in AI ready ({variant}) on port {AI_BUILTIN_PORT}.")
                return True
            time.sleep(0.2)
        _process.kill()
        return _unavailable(f"llama-server was not ready after {START_TIMEOUT} s; "
                            f"see builtin_ai.log")


def _unavailable(reason) -> bool:
    logging.warning(f"Built-in AI unavailable: {reason}")
    ui.show_toast("⚠️ Built-in AI unavailable", str(reason)[:120], ENABLE_TOASTS)
    return False


def stop() -> None:
    """Stop the server this process started (the Job Object does it on a crash)."""
    global _process
    if _process is not None and _process.poll() is None:
        _process.terminate()
        try:
            _process.wait(5)
        except subprocess.TimeoutExpired:
            _process.kill()
    _process = None


# ---------------------------------------------------------------- the provider interface
def ask(raw_text: str, context_text: str | None, instruction: str,
        timeout: float = 15.0) -> str | None:
    if not start():
        return None
    answer = openai_compatible.chat(_url("/v1/chat/completions"), "gemma", "", raw_text,
                                    context_text, instruction, timeout)
    if answer is None and not _healthy():         # it stopped: start it again, once
        logging.warning("The built-in AI stopped; restarting it.")
        if start():
            answer = openai_compatible.chat(_url("/v1/chat/completions"), "gemma", "",
                                            raw_text, context_text, instruction, timeout)
    return answer


def warm_up() -> None:
    start()


def model_name() -> str:
    return f"Gemma 4 E4B · built in ({_variant()})"
