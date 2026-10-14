"""An AI provider for any server that speaks the OpenAI chat/completions format: LM
Studio, the llama.cpp server, vLLM, and cloud services such as OpenAI or Groq.

    AI_PROVIDER="openai"
    AI_URL="http://127.0.0.1:8080/v1/chat/completions"   # your server's address
    AI_MODEL="the-model-id"                              # as the server names it
    AI_API_KEY=""                                        # cloud services only

With a cloud service, what you dictate — and the clipboard text Polish uses as
context — goes to that company's servers. Local servers keep it on this PC.
"""
import logging

import requests

from zeroflow import ui
from zeroflow.settings import AI_API_KEY, AI_MODEL, AI_URL, ENABLE_TOASTS
from zeroflow.vocabulary import _absorb_learned_word


def ask(raw_text: str, context_text: str | None, instruction: str,
        timeout: float = 15.0) -> str | None:
    """The model's answer, or None — with the reason logged and shown as a toast."""
    user = f"Context Window Data:\n{context_text}\n\n" if context_text else ""
    user += f"Input Raw String: {raw_text}\nOutput String:"
    headers = {"Authorization": f"Bearer {AI_API_KEY}"} if AI_API_KEY else {}
    ui.start_processing_spinner("AI Processing")
    try:
        response = requests.post(AI_URL, headers=headers, timeout=timeout, json={
            "model": AI_MODEL,
            "messages": [{"role": "system", "content": instruction},
                         {"role": "user", "content": user}],
            "temperature": 0.2,
        })
    except Exception as e:
        ui.stop_processing_spinner()
        logging.warning(f"AI request failed: {e}")
        ui.show_toast("⚠️ AI Offline", "The AI server did not respond.", ENABLE_TOASTS)
        return None
    ui.stop_processing_spinner()
    if response.status_code != 200:
        logging.warning(f"AI server returned HTTP {response.status_code}: {response.text[:200]}")
        ui.show_toast("⚠️ AI Error", f"The AI server returned HTTP {response.status_code}.",
                      ENABLE_TOASTS)
        return None
    try:
        output = (response.json()["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logging.warning(f"AI server sent an answer in an unexpected shape: {e}")
        return None
    if not output:
        logging.warning("AI server returned an empty answer.")
        return None
    return _absorb_learned_word(output, heard=raw_text) or None


def warm_up() -> None:
    """Nothing to do: such a server loads its model itself."""


def model_name() -> str:
    return AI_MODEL or "(the server's default model)"
