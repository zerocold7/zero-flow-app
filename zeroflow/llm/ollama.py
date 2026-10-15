"""An AI provider for a local Ollama server: model discovery, requests, warm-up."""
import logging

import requests

from zeroflow import ui
from zeroflow.llm.base import user_message
from zeroflow.settings import (ENABLE_TOASTS, FALLBACK_LLM, OLLAMA_HOST_URL,
                               OLLAMA_KEEP_ALIVE, OLLAMA_MODEL_NAME, OLLAMA_NUM_CTX)

_ollama_model = None      # resolved once, on first use


def discover_ollama_model() -> tuple[str, bool]:
    """Choose the LLM to use, in priority order:
      1. OLLAMA_MODEL_NAME from .env, if set — pins an exact model (e.g. qwen2.5:7b).
      2. Otherwise the first model installed in Ollama.
      3. Otherwise FALLBACK_LLM (used when Ollama is unreachable).
    Returns (name, settled): settled is False for the fallback, which is only a guess
    until Ollama answers."""
    if OLLAMA_MODEL_NAME:
        return OLLAMA_MODEL_NAME, True
    try:
        tags_url = OLLAMA_HOST_URL.replace("/api/generate", "/api/tags")
        response = requests.get(tags_url, timeout=2)
        if response.status_code == 200 and response.json().get("models"):
            return response.json()["models"][0]["name"], True
    except Exception:
        pass
    return FALLBACK_LLM, False


def get_ollama_model() -> str:
    """The active LLM name, discovered lazily on first use and cached once Ollama has
    answered. Lazy so the reader does not pay for discovery unless it cleans text.

    The fallback is never cached: with Ollama down at the first Polish, caching it
    bound the whole session to a model that may not be installed, so every request
    after Ollama started got a 404."""
    global _ollama_model
    if _ollama_model is None:
        name, settled = discover_ollama_model()
        if not settled:
            return name
        _ollama_model = name
        logging.info(f"LLM bound to '{_ollama_model}'.")
    return _ollama_model


def _ollama_options() -> dict:
    """Model options for every request, warm-up included — they must match, or Ollama
    reloads the model."""
    options = {"temperature": 0.2}
    if OLLAMA_NUM_CTX > 0:
        options["num_ctx"] = OLLAMA_NUM_CTX
    return options


def ask(raw_text: str, context_text: str | None, instruction: str,
        timeout: float = 15.0) -> str | None:
    """Ollama's answer, or None when it did not answer (unreachable or an HTTP error)."""
    try:
        response = requests.post(
            OLLAMA_HOST_URL,
            json={"model": get_ollama_model(),
                  "prompt": f"{instruction}\n\n{user_message(raw_text, context_text)}",
                  "stream": False,
                  "options": _ollama_options(),
                  # Reasoning models (gemma4) otherwise write ~800 hidden tokens before
                  # a one-line answer: 5-9 s instead of 0.8 s, same result. Models
                  # without reasoning accept and ignore it.
                  "think": False,
                  "keep_alive": OLLAMA_KEEP_ALIVE},
            timeout=timeout,
        )
    except Exception as e:
        logging.warning(f"Ollama request failed: {e}")
        ui.show_toast("⚠️ LLM Offline", "Ollama API failed to respond.", ENABLE_TOASTS)
        return None
    if response.status_code == 200:
        return response.json().get("response") or ""
    # Typically a model name Ollama does not have (404). Without this the text just
    # comes back unpolished and nothing anywhere says why.
    logging.warning(f"Ollama returned HTTP {response.status_code}: {response.text[:200]}")
    ui.show_toast("⚠️ LLM Error", f"Ollama returned HTTP {response.status_code}.", ENABLE_TOASTS)
    return None


def warm_up() -> None:
    """Load the model into Ollama ahead of the first Polish or Translate, so that one
    is not the 3-12 s reload. Run on a background thread; stays quiet if Ollama is
    not running (the first real request then reports it)."""
    model = get_ollama_model()
    try:
        # The same options as every request: a different context size would make
        # Ollama load the model again on the first Polish.
        response = requests.post(OLLAMA_HOST_URL, json={"model": model,
                                                        "keep_alive": OLLAMA_KEEP_ALIVE,
                                                        "options": _ollama_options()},
                                 timeout=120)
    except Exception as e:
        logging.info(f"LLM warm-up skipped: {e}")
        return
    if response.status_code == 200:
        logging.info(f"LLM '{model}' loaded ahead of first use.")
    else:                                        # typically 404: no model by that name
        logging.warning(f"LLM warm-up failed for '{model}': HTTP {response.status_code} "
                        f"{response.text[:200]}")


def model_name() -> str:
    return get_ollama_model()
