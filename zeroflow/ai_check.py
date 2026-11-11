"""The first-run wizard's AI test, as a child process (zeroflow.first_run.real_ask).

It reads the wizard's choices from the temporary settings file ZEROFLOW_SETTINGS names,
and the API key, if any, from the first line of its standard input. It asks the AI
through the Engine's own code (zeroflow.llm) and prints one JSON line: the answer, or
why there is none. A built-in AI it starts ends with this process.
"""
import json
import sys
from urllib.parse import urlparse

INSTRUCTION = ("Correct the capitalisation and punctuation of the text. Reply with the "
               "corrected text only.")


def main() -> dict:
    key = sys.stdin.readline().rstrip("\r\n")
    from zeroflow import settings
    if key:
        settings.AI_API_KEY = key                 # before zeroflow.llm reads it
    from zeroflow import llm
    wanted = settings.AI_PROVIDER
    if wanted == "custom":
        wanted = "claude" if urlparse(settings.AI_URL).hostname == "api.anthropic.com" else "openai"
    if llm.provider is not llm.PROVIDERS.get(wanted):
        return {"answer": None, "why": settings.problems[-1] if settings.problems
                else f"the {wanted} AI is not available"}
    if wanted == "builtin" and not llm.builtin.start(wait=None):
        return {"answer": None, "why": "the built-in AI could not start (details in "
                                       "builtin_ai.log, in the logs folder)"}
    from zeroflow.first_run import AI_TEST_TEXT
    answer = llm.ask_ai(AI_TEST_TEXT, None, INSTRUCTION, timeout=120)
    return {"answer": answer, "why": None if answer else f"the {wanted} AI gave no answer"}


if __name__ == "__main__":
    try:
        result = main()
    except Exception as e:
        result = {"answer": None, "why": f"{type(e).__name__}: {e}"}
    print(json.dumps(result), flush=True)
