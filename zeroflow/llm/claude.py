"""An AI provider for Anthropic's Claude, with the user's own API key.

    AI_PROVIDER="claude"
    AI_API_KEY="sk-ant-..."        # blank: the key from ANTHROPIC_API_KEY or `ant auth login`
    AI_MODEL=""                    # blank: claude-opus-5-5; claude-sonnet-5-5 or
                                   # claude-haiku-5-5 cost less

Uses Anthropic's Python SDK (imported only when this provider is chosen). What you
dictate — and the clipboard text Polish uses as context — is sent to Anthropic.
"""
import logging

from zeroflow import ui
from zeroflow.llm.base import user_message
from zeroflow.settings import AI_API_KEY, AI_MODEL, ENABLE_TOASTS

DEFAULT_MODEL = "claude-opus-5-5"
# Re-run a request the model declines on another model, server-side; "default" routes
# by the reason it declined. (Opus 5.5 takes no temperature, and its thinking cannot be
# switched off: effort is the control, and clean-up needs little of it.)
FALLBACK_BETA = "server-side-fallback-2026-07-01"

_clients = {}


def _make_client(api_key: str):
    import anthropic
    return anthropic.Anthropic(api_key=api_key or None)


def _get_client():
    if AI_API_KEY not in _clients:
        _clients[AI_API_KEY] = _make_client(AI_API_KEY)
    return _clients[AI_API_KEY]


def _no_answer(reason: str, toast: str) -> None:
    logging.warning(f"Claude gave no answer: {reason}")
    ui.show_toast("⚠️ Claude unavailable", toast, ENABLE_TOASTS)
    return None


def ask(raw_text: str, context_text: str | None, instruction: str,
        timeout: float = 15.0) -> str | None:
    """Claude's answer, or None — with the reason logged and shown as a toast."""
    import anthropic
    try:
        response = _get_client().with_options(timeout=timeout).beta.messages.create(
            model=AI_MODEL or DEFAULT_MODEL,
            max_tokens=16000,
            system=instruction,
            messages=[{"role": "user", "content": user_message(raw_text, context_text)}],
            output_config={"effort": "low"},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except anthropic.AuthenticationError:
        return _no_answer("the API key was rejected (401)", "The API key was rejected.")
    except anthropic.PermissionDeniedError:
        return _no_answer("the API key may not use this model (403)",
                          "The API key may not use this model.")
    except anthropic.RateLimitError:
        return _no_answer("rate limited (429)", "Too many requests — try again shortly.")
    except anthropic.APIStatusError as e:
        return _no_answer(f"HTTP {e.status_code}: {e.message}", f"Claude returned HTTP {e.status_code}.")
    except anthropic.APIConnectionError as e:
        return _no_answer(f"could not connect ({e})", "Could not reach Anthropic.")
    if response.stop_reason == "refusal":
        return _no_answer("the request was declined", "Claude declined this text.")
    return "".join(block.text for block in response.content if block.type == "text")


def warm_up() -> None:
    """Nothing to load: the model runs at Anthropic."""


def unload() -> bool:
    """Nothing to unload: the model runs at Anthropic."""
    return False


def model_name() -> str:
    return f"{AI_MODEL or DEFAULT_MODEL} (Anthropic)"
