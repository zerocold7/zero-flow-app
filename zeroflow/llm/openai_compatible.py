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
from zeroflow.llm.base import user_message
from zeroflow.settings import AI_API_KEY, AI_MODEL, AI_URL, ENABLE_TOASTS


def ask(raw_text: str, context_text: str | None, instruction: str,
        timeout: float = 15.0) -> str | None:
    return chat(AI_URL, AI_MODEL, AI_API_KEY, raw_text, context_text, instruction, timeout)


def chat(url: str, model: str, api_key: str, raw_text: str, context_text: str | None,
         instruction: str, timeout: float = 15.0) -> str | None:
    """One request to a chat/completions server at `url` — also used by the built-in
    provider, whose llama-server speaks this format."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        response = requests.post(url, headers=headers, timeout=timeout, json={
            "model": model,
            "messages": [{"role": "system", "content": instruction},
                         {"role": "user", "content": user_message(raw_text, context_text)}],
            "temperature": 0.2,
        })
    except Exception as e:
        logging.warning(f"AI request failed: {e}")
        ui.show_toast("⚠️ AI Offline", "The AI server did not respond.", ENABLE_TOASTS)
        return None
    if response.status_code != 200:
        logging.warning(f"AI server returned HTTP {response.status_code}: {response.text[:200]}")
        ui.show_toast("⚠️ AI Error", f"The AI server returned HTTP {response.status_code}.",
                      ENABLE_TOASTS)
        return None
    try:
        return response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logging.warning(f"AI server sent an answer in an unexpected shape: {e}")
        return None


def warm_up() -> None:
    """Nothing to do: such a server loads its model itself."""


def unload() -> bool:
    """Nothing to do: the server manages its own memory."""
    return False


def model_name() -> str:
    return AI_MODEL or "(the server's default model)"
