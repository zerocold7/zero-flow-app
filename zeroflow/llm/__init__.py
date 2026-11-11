"""The AI model, whichever provider runs it.

The engine and the reader call ask_ai, warm_up_ai, unload_ai and model_name; each hands the call
to the active provider (zeroflow.llm.base.Provider), chosen with AI_PROVIDER in the settings:

    builtin  llama-server, run by the engine itself (llm.builtin) — the default
    ollama   a local Ollama server (llm.ollama)
    openai   any server speaking the OpenAI chat format (llm.openai_compatible):
             LM Studio, the llama.cpp server, vLLM, or a cloud service
    claude   Anthropic's Claude, with an API key (llm.claude)

What every answer goes through, whoever gave it, happens here once: the console
spinner, the empty-answer check, and learning a word the model tagged `[LEARN: …]`.
"""
import logging
import traceback
from urllib.parse import urlparse

from zeroflow import settings, ui
from zeroflow.llm import builtin, claude, ollama, openai_compatible
from zeroflow.vocabulary import LEARN_PATTERN, absorb_learned_word

PROVIDERS = {"builtin": builtin, "ollama": ollama, "openai": openai_compatible, "claude": claude}


def choose(name: str):
    """The provider called `name`; Ollama, with the mistake reported, if there is none.
    "custom" is Claude when its address is Anthropic's, otherwise any OpenAI-format server."""
    if name == "custom":
        name = "claude" if urlparse(settings.AI_URL).hostname == "api.anthropic.com" else "openai"
    if name == "builtin" and not builtin.available():
        settings.problems.append("The built-in AI is not installed on this PC — run "
                                 "tools/get_llama.py, or set AI_PROVIDER=ollama. Using ollama.")
        return ollama
    if name == "claude" and not claude.available():
        settings.problems.append('AI_PROVIDER="claude" needs Anthropic\'s package — install it '
                                 'with: venv\\Scripts\\python -m pip install anthropic -c '
                                 'constraints.txt. Using the built-in AI.')
        return choose("builtin")
    if name in PROVIDERS:
        return PROVIDERS[name]
    settings.problems.append(f'AI_PROVIDER="{name}" in the settings is not one of '
                             f'{", ".join(PROVIDERS)} — using ollama.')
    return ollama


provider = choose(settings.AI_PROVIDER)


def clipboard_context_allowed(chosen) -> bool:
    """Whether Polish may hand `chosen` the clipboard (POLISH_CLIPBOARD_CONTEXT). Decided
    by the provider actually in use, not the one the settings named: the built-in AI falls back
    to Ollama when it is not installed, and that Ollama may be on another computer."""
    name = next(key for key, module in PROVIDERS.items() if module is chosen)
    return settings.clipboard_context_sent(settings.POLISH_CLIPBOARD_CONTEXT, name,
                                           settings.AI_URL, settings.OLLAMA_HOST_URL)


SEND_CLIPBOARD_CONTEXT = clipboard_context_allowed(provider)


def ask_ai(raw_text: str, context_text: str | None, instruction: str,
           timeout: float = 15.0, learn: bool = False) -> str | None:
    """The model's answer, or None when there is none (the reason is logged and shown).

    `learn`: keep a word the model tagged `[LEARN: …]` — only English Polish, whose
    prompt asks for it. Elsewhere the tag is only removed: text the user selected (F4,
    Shift+F3) could otherwise carry one and teach a "word" that primes every dictation."""
    ui.start_processing_spinner("AI Processing")
    try:
        answer = provider.ask(raw_text, context_text, instruction, timeout)
    except Exception:
        # A provider bug, a missing package, a server answering in a shape nobody
        # expected: no answer. Raised, it would lose the dictation — the caller
        # pastes what was said when there is no answer.
        logging.error(f"The AI provider failed: {traceback.format_exc()}")
        ui.show_toast("⚠️ AI Error", "The AI failed — your own words were kept.",
                      settings.ENABLE_TOASTS)
        answer = None
    finally:
        ui.stop_processing_spinner()
    if answer is None:
        return None
    if not answer.strip():
        logging.warning("The AI returned an empty answer.")
        return None
    if not learn:
        return LEARN_PATTERN.sub("", answer).strip() or None
    return absorb_learned_word(answer.strip(), heard=raw_text) or None


def warm_up_ai() -> None:
    provider.warm_up()


def unload_ai() -> bool:
    """Free the AI model's memory until the next request loads it again."""
    return provider.unload()


def model_name() -> str:
    return provider.model_name()
