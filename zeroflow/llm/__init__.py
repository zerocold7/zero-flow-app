"""The AI model, whichever provider runs it.

The engine and the reader call these four functions; each hands the call to the active
provider (zeroflow.llm.base.Provider), chosen with AI_PROVIDER in .env:

    ollama   a local Ollama server (llm.ollama) — the default
    openai   any server speaking the OpenAI chat format (llm.openai_compatible):
             LM Studio, the llama.cpp server, vLLM, or a cloud service
"""
from zeroflow import settings
from zeroflow.llm import ollama, openai_compatible

PROVIDERS = {"ollama": ollama, "openai": openai_compatible}


def choose(name: str):
    """The provider called `name`; Ollama, with the mistake reported, if there is none."""
    if name in PROVIDERS:
        return PROVIDERS[name]
    settings.problems.append(f'AI_PROVIDER="{name}" in .env is not one of '
                             f'{", ".join(PROVIDERS)} — using ollama.')
    return ollama


provider = choose(settings.AI_PROVIDER)


def ask_ai(raw_text: str, context_text: str | None, instruction: str,
           timeout: float = 15.0) -> str | None:
    """The model's answer, or None when there is none (the reason is logged)."""
    return provider.ask(raw_text, context_text, instruction, timeout)


def query_ai(raw_text: str, context_text: str | None, instruction: str,
             timeout: float = 15.0) -> str:
    """The model's answer, or `raw_text` when there is none — for callers that carry
    on with the original either way. Callers that must tell the user use ask_ai."""
    return ask_ai(raw_text, context_text, instruction, timeout) or raw_text


def warm_up_ai() -> None:
    provider.warm_up()


def model_name() -> str:
    return provider.model_name()
