"""The AI model, whichever provider runs it.

The engine and the reader call ask_ai, warm_up_ai and model_name; each hands the call
to the active provider (zeroflow.llm.base.Provider), chosen with AI_PROVIDER in .env:

    builtin  llama-server, run by the engine itself (llm.builtin) — the default
    ollama   a local Ollama server (llm.ollama)
    openai   any server speaking the OpenAI chat format (llm.openai_compatible):
             LM Studio, the llama.cpp server, vLLM, or a cloud service
    claude   Anthropic's Claude, with an API key (llm.claude)

What every answer goes through, whoever gave it, happens here once: the console
spinner, the empty-answer check, and learning a word the model tagged `[LEARN: …]`.
"""
import logging

from zeroflow import settings, ui
from zeroflow.llm import builtin, claude, ollama, openai_compatible
from zeroflow.vocabulary import absorb_learned_word

PROVIDERS = {"builtin": builtin, "ollama": ollama, "openai": openai_compatible, "claude": claude}


def choose(name: str):
    """The provider called `name`; Ollama, with the mistake reported, if there is none."""
    if name == "builtin" and not builtin.available():
        settings.problems.append("The built-in AI is not installed on this PC — run "
                                 "tools/get_llama.py, or set AI_PROVIDER=ollama. Using ollama.")
        return ollama
    if name in PROVIDERS:
        return PROVIDERS[name]
    settings.problems.append(f'AI_PROVIDER="{name}" in .env is not one of '
                             f'{", ".join(PROVIDERS)} — using ollama.')
    return ollama


provider = choose(settings.AI_PROVIDER)


def ask_ai(raw_text: str, context_text: str | None, instruction: str,
           timeout: float = 15.0) -> str | None:
    """The model's answer, or None when there is none (the reason is logged and shown)."""
    ui.start_processing_spinner("AI Processing")
    try:
        answer = provider.ask(raw_text, context_text, instruction, timeout)
    finally:
        ui.stop_processing_spinner()
    if answer is None:
        return None
    if not answer.strip():
        logging.warning("The AI returned an empty answer.")
        return None
    return absorb_learned_word(answer.strip(), heard=raw_text) or None


def warm_up_ai() -> None:
    provider.warm_up()


def model_name() -> str:
    return provider.model_name()
