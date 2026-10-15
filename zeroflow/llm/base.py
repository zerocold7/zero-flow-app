"""What an AI provider gives the engine.

The engine never calls a provider directly: it calls zeroflow.llm (ask_ai, warm_up_ai,
model_name), which hands the call to the active provider. A provider is a module with
these three functions, so adding one changes nothing in the engine.
"""
from typing import Protocol


class Provider(Protocol):
    def ask(self, raw_text: str, context_text: str | None, instruction: str,
            timeout: float = 15.0) -> str | None:
        """The model's raw answer to `instruction` applied to `raw_text`, or None when
        it did not answer (not reachable, or an error) — with the reason logged and
        shown. zeroflow.llm does the rest (the spinner, an empty answer, [LEARN: …])."""

    def warm_up(self) -> None:
        """Load the model ahead of the first request; quiet if that is not possible."""

    def model_name(self) -> str:
        """The model in use, as shown in the start-up banner."""


def user_message(raw_text: str, context_text: str | None) -> str:
    """The words to work on, after the clipboard context Polish hands over, if any."""
    message = f"Context Window Data:\n{context_text}\n\n" if context_text else ""
    return message + f"Input Raw String: {raw_text}\nOutput String:"
