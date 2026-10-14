"""The AI model, whichever provider runs it.

The engine and the reader call these four functions; each hands the call to the active
provider (zeroflow.llm.base.Provider). Today that is Ollama, a separate local server
(llm.ollama). Phase 4 adds a model built into the engine as a second provider.
"""
from zeroflow.llm import ollama

provider = ollama


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
