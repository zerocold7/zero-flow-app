"""What an AI provider gives the engine.

The engine never calls a provider directly: it calls zeroflow.llm (ask_ai, query_ai,
warm_up_ai, model_name), which hands the call to the active provider. A provider is a
module with these three functions, so adding one — the built-in model of phase 4 —
changes nothing in the engine.
"""
from typing import Protocol


class Provider(Protocol):
    def ask(self, raw_text: str, context_text: str | None, instruction: str,
            timeout: float = 15.0) -> str | None:
        """The model's answer to `instruction` applied to `raw_text`, or None when it
        did not answer (not reachable, an error, or an empty reply) — with the reason
        logged and shown, so callers only decide what to paste."""

    def warm_up(self) -> None:
        """Load the model ahead of the first request; quiet if that is not possible."""

    def model_name(self) -> str:
        """The model in use, as shown in the start-up banner."""
